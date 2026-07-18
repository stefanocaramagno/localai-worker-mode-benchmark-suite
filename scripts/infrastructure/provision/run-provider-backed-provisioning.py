#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Tuple

try:
    import yaml
except ImportError:
    yaml = None


def _load_artifact_path_helpers():
    import importlib.util

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "common" / "artifact_paths.py"
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("artifact_paths", candidate)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            return module.normalize_artifact_payload_for_output, module.normalize_artifact_text_for_output
    raise RuntimeError("Unable to locate scripts/common/artifact_paths.py")


normalize_artifact_payload_for_output, normalize_artifact_text_for_output = _load_artifact_path_helpers()


VALID_ACTIONS = {"plan", "provision", "kubeconfig", "destroy"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4)
        handle.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def repo_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def rel_or_abs(path: Optional[Path], repo_root: Path) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def bool_from_optional(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def has_path_component(value: str) -> bool:
    return any(separator in value for separator in ("/", "\\")) or Path(value).parent != Path(".")


def tool_candidate_record(path: Optional[Path], source: str) -> Dict[str, Any]:
    exists = bool(path and path.exists())
    executable = bool(exists and path and path.is_file())
    return {
        "source": source,
        "path": path.as_posix() if path else None,
        "exists": exists,
        "isFile": bool(path and path.is_file()) if path else False,
        "selected": False,
        "executableCandidate": executable,
    }


def resolve_provider_tool(repo_root: Path, requested_tool_path: str) -> Tuple[Optional[str], Dict[str, Any]]:
    requested_input = (requested_tool_path or "").strip()
    env_override = (os.environ.get("PROXMOX_K3S_TOOL_PATH") or "").strip()
    requested = env_override if env_override and requested_input in {"", "proxmox-k3s"} else (requested_input or "proxmox-k3s")
    candidates: List[Dict[str, Any]] = []

    def add_path_candidate(path: Optional[Path], source: str) -> None:
        candidates.append(tool_candidate_record(path, source))

    def add_with_platform_extensions(path: Path, source: str) -> None:
        add_path_candidate(path, source)
        if os.name == "nt" and path.suffix.lower() != ".exe":
            add_path_candidate(path.with_suffix(path.suffix + ".exe") if path.suffix else Path(str(path) + ".exe"), f"{source}:windows-exe")

    path_match = shutil.which(requested)
    if path_match:
        resolved = Path(path_match).resolve()
        selected = tool_candidate_record(resolved, "path-lookup")
        selected["selected"] = True
        candidates.append(selected)
        return str(resolved), {
            "status": "resolved",
            "requestedPath": requested,
            "environmentOverrideUsed": bool(env_override and requested == env_override),
            "resolvedPath": str(resolved),
            "resolutionSource": "path-lookup",
            "candidates": candidates,
        }
    candidates.append({
        "source": "path-lookup",
        "path": requested,
        "exists": False,
        "isFile": False,
        "selected": False,
        "executableCandidate": False,
    })

    requested_path = Path(requested)

    if requested_path.is_absolute():
        add_with_platform_extensions(requested_path, "explicit-absolute-path")
    elif has_path_component(requested):
        add_with_platform_extensions((Path.cwd() / requested_path).resolve(), "explicit-relative-to-cwd")
        add_with_platform_extensions((repo_root / requested_path).resolve(), "explicit-relative-to-repo-root")
    else:
        names = [requested]
        if os.name == "nt" and not requested.lower().endswith(".exe"):
            names.append(f"{requested}.exe")

        common_dirs = [
            repo_root,
            repo_root / "bin",
            repo_root / "tools",
            repo_root / "tools" / requested,
            repo_root / "tools" / requested / "bin",
            repo_root / "external" / requested,
            repo_root / "external" / requested / "bin",
            repo_root.parent / requested / "bin",
            repo_root.parent / requested,
            repo_root.parent / requested / "build",
            repo_root.parent / requested / "dist",
            repo_root.parent / requested / "cmd",
        ]
        for directory in common_dirs:
            for name in names:
                add_path_candidate((directory / name).resolve(), f"common-local-layout:{directory.as_posix()}")

    for candidate in candidates:
        candidate_path = candidate.get("path")
        if not candidate.get("executableCandidate") or not candidate_path:
            continue
        resolved = str(Path(candidate_path).resolve())
        candidate["selected"] = True
        return resolved, {
            "status": "resolved",
            "requestedPath": requested,
            "environmentOverrideUsed": bool(env_override and requested == env_override),
            "resolvedPath": resolved,
            "resolutionSource": candidate.get("source"),
            "candidates": candidates,
        }

    return None, {
        "status": "unresolved",
        "requestedPath": requested,
        "environmentOverrideUsed": bool(env_override and requested == env_override),
        "resolvedPath": None,
        "resolutionSource": None,
        "candidates": candidates,
        "hint": (
            "Provider executable not found. Provide an absolute path with --tool-path, "
            "place the executable in PATH, or keep the provider checkout/binary in a supported "
            "repository-local or sibling directory layout."
        ),
    }


def load_cycle(repo_root: Path, cycle_config: str) -> Tuple[Path, Dict[str, Any]]:
    cycle_path = repo_path(repo_root, cycle_config)
    if cycle_path is None or not cycle_path.exists():
        raise FileNotFoundError(f"Cycle profile not found: {cycle_config}")
    return cycle_path, read_json(cycle_path)


def resolve_infrastructure_profile(repo_root: Path, cycle: Dict[str, Any]) -> Tuple[Optional[Path], Dict[str, Any]]:
    infra_path_value = (
        cycle.get("providerBackedInfrastructure", {}).get("infrastructureProfilePath")
        or cycle.get("infrastructureProfile", {}).get("profilePath")
        or cycle.get("infrastructureProfile", {}).get("infrastructureProfilePath")
    )
    infra_path = repo_path(repo_root, infra_path_value)
    if infra_path is None or not infra_path.exists():
        return infra_path, {}
    return infra_path, read_json(infra_path)


def resolve_provider_binding(repo_root: Path, cycle: Dict[str, Any], infra_profile: Dict[str, Any]) -> Tuple[Path, Dict[str, Any]]:
    binding_path_value = (
        cycle.get("providerBackedInfrastructure", {}).get("providerBindingPath")
        or infra_profile.get("provider", {}).get("providerBindingPath")
    )
    binding_path = repo_path(repo_root, binding_path_value)
    if binding_path is None or not binding_path.exists():
        raise FileNotFoundError(f"Provider binding not found: {binding_path_value}")
    return binding_path, read_json(binding_path)


def resolve_lifecycle_policy(repo_root: Path, cycle: Dict[str, Any], binding: Dict[str, Any]) -> Tuple[Optional[Path], Dict[str, Any]]:
    policy_path_value = (
        cycle.get("clusterLifecycle", {}).get("lifecyclePolicyPath")
        or cycle.get("providerBackedInfrastructure", {}).get("lifecyclePolicyPath")
        or binding.get("clusterLifecycle", {}).get("lifecyclePolicyPath")
        or binding.get("lifecycleCompatibility", {}).get("lifecyclePolicyPath")
    )
    policy_path = repo_path(repo_root, policy_path_value)
    if policy_path is None or not policy_path.exists():
        return policy_path, {}
    return policy_path, read_json(policy_path)


def resolve_provisioning_profile(
    repo_root: Path,
    cycle: Dict[str, Any],
    explicit_profile: Optional[str],
) -> Tuple[Optional[Path], Dict[str, Any]]:
    profile_value = explicit_profile or cycle.get("pipelineProfiles", {}).get("provisioningIntegration")
    if not profile_value:
        return None, {}
    profile_path = repo_path(repo_root, profile_value)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Provisioning integration profile not found: {profile_value}")
    return profile_path, read_json(profile_path)


def _provider_config_kind_for_path(provider_config: Dict[str, Any], selected_path: Optional[Path], repo_root: Path, fallback_key: str) -> str:
    if selected_path is None:
        return fallback_key
    try:
        selected_resolved = selected_path.resolve()
    except Exception:
        selected_resolved = selected_path
    for key, value in provider_config.items():
        if not key.endswith("Path") or not value:
            continue
        candidate = repo_path(repo_root, value)
        if candidate is None:
            continue
        try:
            candidate_resolved = candidate.resolve()
        except Exception:
            candidate_resolved = candidate
        if candidate_resolved == selected_resolved:
            return key
    return fallback_key


def resolve_provider_config(
    repo_root: Path,
    binding: Dict[str, Any],
    provisioning_profile: Dict[str, Any],
    action: str,
    dry_run: bool,
    override: Optional[str],
) -> Tuple[Optional[Path], str, List[Dict[str, Any]], Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    provider_config = binding.get("providerConfig", {})
    binding_resolution = binding.get("resolutionPolicy", {})
    profile_resolution = provisioning_profile.get("providerConfigResolution", {})

    resolution_mode = "reviewOrDryRun" if (dry_run or action == "plan") else "realExecution"
    real_execution = resolution_mode == "realExecution"

    if real_execution:
        order = (
            profile_resolution.get("realExecutionConfigPreferenceOrder")
            or binding_resolution.get("realExecutionConfigPreferenceOrder")
            or ["localPath"]
        )
        order_source = "profile" if profile_resolution.get("realExecutionConfigPreferenceOrder") else ("binding" if binding_resolution.get("realExecutionConfigPreferenceOrder") else "built_in")
        forbidden_kinds = set((profile_resolution.get("resolutionModes", {}).get("realExecution", {}) or {}).get("forbiddenConfigKinds") or ["examplePath", "templatePath"])
        allow_example_for_real = bool(profile_resolution.get("allowExampleConfigForRealExecution", False) or binding_resolution.get("allowExampleForCreateDelete", False))
    else:
        order = (
            profile_resolution.get("reviewOrDryRunConfigPreferenceOrder")
            or binding_resolution.get("reviewOrDryRunConfigPreferenceOrder")
            or ["examplePath", "templatePath"]
        )
        order_source = "profile" if profile_resolution.get("reviewOrDryRunConfigPreferenceOrder") else ("binding" if binding_resolution.get("reviewOrDryRunConfigPreferenceOrder") else "built_in")
        forbidden_kinds = set()
        allow_example_for_real = False

    if override:
        path = repo_path(repo_root, override)
        override_kind = _provider_config_kind_for_path(provider_config, path, repo_root, "explicitOverride")
        candidates.append({
            "key": "explicitOverride",
            "providerConfigKind": override_kind,
            "path": path,
            "exists": bool(path and path.exists()),
            "selected": False,
            "source": "command_line_override",
        })

    for key in order:
        path = repo_path(repo_root, provider_config.get(key))
        candidates.append({
            "key": key,
            "providerConfigKind": key,
            "path": path,
            "exists": bool(path and path.exists()),
            "selected": False,
            "source": f"{resolution_mode}_preference_order",
        })

    selected: Optional[Path] = None
    selected_key = "unresolved"
    selected_kind = "unresolved"
    for candidate in candidates:
        if not candidate["exists"]:
            continue
        kind = candidate.get("providerConfigKind") or candidate.get("key")
        if real_execution and kind in forbidden_kinds and not allow_example_for_real:
            candidate["rejected"] = True
            candidate["rejectionReason"] = "review_only_config_not_allowed_for_real_execution"
            continue
        selected = candidate["path"]
        selected_key = candidate["key"]
        selected_kind = kind
        candidate["selected"] = True
        break

    if selected is None and override:
        selected_key = "override_missing_or_rejected"

    normalized = []
    for candidate in candidates:
        normalized.append({
            "key": candidate["key"],
            "providerConfigKind": candidate.get("providerConfigKind"),
            "source": candidate.get("source"),
            "path": rel_or_abs(candidate["path"], repo_root),
            "exists": candidate["exists"],
            "selected": candidate["selected"],
            "rejected": bool(candidate.get("rejected", False)),
            "rejectionReason": candidate.get("rejectionReason"),
        })

    resolution_context = {
        "resolutionMode": resolution_mode,
        "preferenceOrder": order,
        "preferenceOrderSource": order_source,
        "selectionPrecedence": ["explicitOverride", "modeSpecificPreferenceOrder"],
        "selectedProviderConfigKind": selected_kind,
        "realExecution": real_execution,
        "reviewOnlyKindsForbiddenForRealExecution": sorted(forbidden_kinds) if real_execution else [],
    }

    return selected, selected_key, normalized, resolution_context


def parse_provider_config_identity(provider_config_path: Optional[Path]) -> Dict[str, Any]:
    if provider_config_path is None or not provider_config_path.exists():
        return {"status": "unavailable", "path": provider_config_path.as_posix() if provider_config_path else None}
    try:
        text = provider_config_path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        return {"status": "unreadable", "path": provider_config_path.as_posix(), "error": str(exc)}

    cluster_format = "single_cluster_legacy"
    cluster_match = re.search(r"(?m)^\s*cluster_name\s*:\s*([^#\n]+)", text)
    kubeconfig_match = re.search(r"(?m)^\s*kubeconfig_path\s*:\s*([^#\n]+)", text)

    if re.search(r"(?m)^clusters\s*:", text):
        cluster_format = "clusters_list"
        cluster_match = re.search(r"(?m)^\s*-\s*name\s*:\s*([^#\n]+)", text)
        kubeconfig_match = re.search(r"(?m)^\s*kubeconfig_path\s*:\s*([^#\n]+)", text)

    ips = []
    for match in re.finditer(r"(?m)^\s*ip\s*:\s*([0-9]{1,3}(?:\.[0-9]{1,3}){3})\s*(?:#.*)?$", text):
        value = match.group(1).strip()
        if value not in ips:
            ips.append(value)
    return {
        "status": "parsed",
        "path": provider_config_path.as_posix(),
        "providerConfigFormat": cluster_format,
        "clusterName": cluster_match.group(1).strip().strip('"\'') if cluster_match else None,
        "kubeconfigPath": kubeconfig_match.group(1).strip().strip('"\'') if kubeconfig_match else None,
        "ipAddresses": ips,
    }


def expected_binding_identity(binding: Dict[str, Any]) -> Dict[str, Any]:
    variables = binding.get("templateVariables") or {}
    ips: List[str] = []
    template = variables.get("template") or {}
    if template.get("ipAddress"):
        ips.append(str(template.get("ipAddress")))
    for section in ("controlPlane", "workers"):
        for node in variables.get(section, []) or []:
            ip = node.get("ipAddress")
            if ip and str(ip) not in ips:
                ips.append(str(ip))
    return {
        "clusterName": variables.get("clusterName"),
        "kubeconfigPath": variables.get("kubeconfigPath"),
        "ipAddresses": ips,
    }


def expected_kubeconfig_value(
    binding: Dict[str, Any],
    provisioning_profile: Dict[str, Any],
    selected_config: Optional[Path] = None,
) -> Optional[str]:
    selected_identity = parse_provider_config_identity(selected_config)
    return (
        selected_identity.get("kubeconfigPath")
        or provisioning_profile.get("kubeconfigVerification", {}).get("expectedPath")
        or binding.get("providerConfig", {}).get("recommendedKubeconfigPath")
        or binding.get("templateVariables", {}).get("kubeconfigPath")
    )


def prepare_kubeconfig_parent_directory(
    repo_root: Path,
    binding: Dict[str, Any],
    provisioning_profile: Dict[str, Any],
    selected_config: Optional[Path],
    action: str,
    dry_run: bool,
) -> Dict[str, Any]:
    kubeconfig_value = expected_kubeconfig_value(binding, provisioning_profile, selected_config)
    kubeconfig_path = repo_path(repo_root, kubeconfig_value)
    required = action in {"provision", "kubeconfig"} and kubeconfig_path is not None
    parent_path = kubeconfig_path.parent if kubeconfig_path else None
    existed_before = bool(parent_path and parent_path.exists())
    created = False
    error = None

    if required and parent_path and not dry_run:
        try:
            parent_path.mkdir(parents=True, exist_ok=True)
            created = not existed_before and parent_path.exists()
        except Exception as exc:
            error = str(exc)

    existed_after = bool(parent_path and parent_path.exists())
    if not required:
        status = "not_required"
    elif dry_run:
        status = "not_enforced_dry_run"
    elif error:
        status = "failed"
    elif existed_after:
        status = "ready"
    else:
        status = "failed_missing_parent"

    return {
        "required": required,
        "status": status,
        "kubeconfigPath": kubeconfig_value,
        "resolvedKubeconfigPath": rel_or_abs(kubeconfig_path, repo_root),
        "parentDirectory": rel_or_abs(parent_path, repo_root),
        "parentExistedBefore": existed_before,
        "parentCreated": created,
        "parentExistsAfter": existed_after,
        "dryRun": dry_run,
        "error": error,
    }


def build_lifecycle_collision_guard(
    repo_root: Path,
    selected_config: Optional[Path],
    binding: Dict[str, Any],
    provisioning_profile: Dict[str, Any],
    mode: str,
    action: str,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []
    selected_identity = parse_provider_config_identity(selected_config)
    expected_identity = expected_binding_identity(binding)
    kubeconfig_value = expected_kubeconfig_value(binding, provisioning_profile, selected_config) or expected_identity.get("kubeconfigPath")
    kubeconfig_path = repo_path(repo_root, kubeconfig_value)
    preexisting_kubeconfig = bool(kubeconfig_path and kubeconfig_path.exists() and kubeconfig_path.stat().st_size > 0)
    guard_policy = provisioning_profile.get("lifecycleCollisionGuard") or binding.get("lifecycleCollisionGuard") or {}
    enforcement = str(guard_policy.get("enforcement") or "warn_only")

    cluster_name_match = True
    if selected_identity.get("clusterName") and expected_identity.get("clusterName"):
        cluster_name_match = selected_identity.get("clusterName") == expected_identity.get("clusterName")
    if not cluster_name_match:
        message = "Provider configuration cluster_name does not match the selected provider binding."
        if enforcement == "strict":
            errors.append(message)
        else:
            warnings.append(message)

    expected_ips = set(expected_identity.get("ipAddresses") or [])
    selected_ips = set(selected_identity.get("ipAddresses") or [])
    missing_expected_ips = sorted(expected_ips - selected_ips) if selected_ips else []
    unexpected_ips = sorted(selected_ips - expected_ips) if selected_ips and expected_ips else []
    if missing_expected_ips or unexpected_ips:
        message = "Provider configuration IP allocation differs from the selected provider binding."
        if enforcement == "strict":
            errors.append(message)
        else:
            warnings.append(message)

    if mode == "ephemeral" and action == "provision" and preexisting_kubeconfig:
        warnings.append(
            "An existing kubeconfig is present before ephemeral provisioning. This may be a retained artifact from a previous run; verify provider-side cluster state before reusing cluster_name or IP allocations."
        )

    return {
        "enabled": True,
        "enforcement": enforcement,
        "clusterLifecycleMode": mode,
        "action": action,
        "selectedProviderConfigIdentity": selected_identity,
        "expectedProviderBindingIdentity": expected_identity,
        "clusterNameMatch": cluster_name_match,
        "missingExpectedIpAddresses": missing_expected_ips,
        "unexpectedIpAddresses": unexpected_ips,
        "expectedKubeconfigPath": kubeconfig_value,
        "resolvedExpectedKubeconfigPath": rel_or_abs(kubeconfig_path, repo_root),
        "preExistingKubeconfig": preexisting_kubeconfig,
        "decision": {
            "canProceed": not errors,
            "warningCount": len(warnings),
            "errorCount": len(errors),
        },
    }, warnings, errors


def command_for(action_step: str, tool_path: str, provider_config: Path, confirm_delete: bool) -> List[str]:
    if action_step == "create":
        return [tool_path, "cluster", "create", "-c", provider_config.as_posix()]
    if action_step == "kubeconfig":
        return [tool_path, "cluster", "kubeconfig", "-c", provider_config.as_posix()]
    if action_step == "delete":
        return [tool_path, "cluster", "delete", "-c", provider_config.as_posix()]
    raise ValueError(f"Unsupported provider command step: {action_step}")


def _coerce_positive_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _command_timeout_for_step(execution_policy: Dict[str, Any], step_name: str) -> int:
    default_per_step = {
        "create": 5400,
        "kubeconfig": 600,
        "delete": 1800,
    }
    per_step = execution_policy.get("perStepTimeoutSeconds") or {}
    if step_name in per_step:
        return _coerce_positive_int(per_step.get(step_name), default_per_step.get(step_name, 3600))
    fallback = default_per_step.get(step_name, 3600)
    return _coerce_positive_int(execution_policy.get("defaultTimeoutSeconds"), fallback)


def _terminate_process_tree(process: subprocess.Popen, grace_seconds: int, log_handle: TextIO) -> str:
    termination_method = "unknown"
    try:
        if os.name == "nt":
            termination_method = "taskkill_tree"
            try:
                process.terminate()
            except Exception:
                pass
            try:
                process.wait(timeout=max(grace_seconds, 1))
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
        else:
            termination_method = "process_group_sigterm_sigkill"
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                return termination_method
            except Exception as exc:
                log_handle.write(f"\nProviderCommandTerminationWarning: sigterm_failed: {exc}\n")
                try:
                    process.terminate()
                except Exception:
                    pass
            try:
                process.wait(timeout=max(grace_seconds, 1))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except Exception as exc:
                    log_handle.write(f"ProviderCommandTerminationWarning: sigkill_failed: {exc}\n")
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    log_handle.write("ProviderCommandTerminationWarning: process_still_running_after_sigkill\n")
    except Exception as exc:
        log_handle.write(f"ProviderCommandTerminationWarning: {exc}\n")
        try:
            process.kill()
        except Exception:
            pass
    return termination_method


def _start_output_reader(stream: Any, output_queue: "queue.Queue[str]") -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            output_queue.put(line)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _drain_output_queue(output_queue: "queue.Queue[str]", log_handle: TextIO, output_lines: List[str]) -> int:
    drained = 0
    while True:
        try:
            line = output_queue.get_nowait()
        except queue.Empty:
            break
        log_handle.write(line)
        log_handle.flush()
        stripped = line.rstrip("\r\n")
        if stripped.strip():
            output_lines.append(stripped)
        drained += 1
    return drained


def run_command(
    command: List[str],
    log_path: Path,
    dry_run: bool,
    stdin_text: Optional[str] = None,
    working_directory: Optional[Path] = None,
    execution_policy: Optional[Dict[str, Any]] = None,
    step_name: str = "provider_command",
) -> Dict[str, Any]:
    execution_policy = execution_policy or {}
    started_at = utc_now()
    monotonic_start = time.monotonic()
    printable = " ".join(command)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timeout_seconds = _command_timeout_for_step(execution_policy, step_name)
    heartbeat_seconds = _coerce_positive_int(execution_policy.get("heartbeatIntervalSeconds"), 60)
    graceful_termination_seconds = _coerce_positive_int(execution_policy.get("gracefulTerminationSeconds"), 30)
    output_tail_line_count = _coerce_positive_int(execution_policy.get("outputTailLines"), 80)
    stdin_provided = stdin_text is not None
    working_directory_value = working_directory.as_posix() if working_directory else None

    if dry_run:
        write_text(
            log_path,
            f"Dry-run only. Command not executed.\n"
            f"Command: {printable}\n"
            f"StartedAtUtc: {started_at}\n"
            f"StdinProvided: {stdin_provided}\n"
            f"WorkingDirectory: {working_directory_value}\n"
            f"TimeoutSeconds: {timeout_seconds}\n",
        )
        return {
            "printableCommand": printable,
            "logPath": log_path.as_posix(),
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "durationSeconds": 0.0,
            "exitCode": 0,
            "status": "dry_run",
            "timedOut": False,
            "timeoutSeconds": timeout_seconds,
            "stdinProvided": stdin_provided,
            "workingDirectory": working_directory_value,
        }

    output_lines: List[str] = []
    timed_out = False
    timeout_at: Optional[str] = None
    termination_method: Optional[str] = None
    finished_at = started_at
    return_code: Optional[int] = None

    popen_kwargs: Dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.PIPE if stdin_provided else subprocess.DEVNULL,
        "text": True,
        "bufsize": 1,
        "cwd": str(working_directory) if working_directory else None,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    with log_path.open("w", encoding="utf-8") as log_handle:
        log_handle.write(
            f"Command: {printable}\n"
            f"StartedAtUtc: {started_at}\n"
            f"StdinProvided: {stdin_provided}\n"
            f"WorkingDirectory: {working_directory_value}\n"
            f"TimeoutSeconds: {timeout_seconds}\n"
            f"HeartbeatIntervalSeconds: {heartbeat_seconds}\n\n"
        )
        log_handle.flush()

        process = subprocess.Popen(command, **popen_kwargs)
        if stdin_provided and process.stdin:
            try:
                process.stdin.write(stdin_text or "")
                process.stdin.flush()
            finally:
                process.stdin.close()

        output_queue: "queue.Queue[str]" = queue.Queue()
        reader_thread = None
        if process.stdout is not None:
            import threading

            reader_thread = threading.Thread(
                target=_start_output_reader,
                args=(process.stdout, output_queue),
                daemon=True,
            )
            reader_thread.start()

        next_heartbeat = time.monotonic() + heartbeat_seconds
        while True:
            _drain_output_queue(output_queue, log_handle, output_lines)
            return_code = process.poll()
            if return_code is not None:
                break

            elapsed = time.monotonic() - monotonic_start
            if elapsed > timeout_seconds:
                timed_out = True
                timeout_at = utc_now()
                log_handle.write(
                    f"\nProviderCommandTimeout: step={step_name} "
                    f"elapsedSeconds={elapsed:.1f} timeoutSeconds={timeout_seconds}\n"
                )
                log_handle.flush()
                termination_method = _terminate_process_tree(process, graceful_termination_seconds, log_handle)
                return_code = process.poll()
                break

            if heartbeat_seconds > 0 and time.monotonic() >= next_heartbeat:
                log_handle.write(
                    f"ProviderCommandHeartbeat: step={step_name} "
                    f"elapsedSeconds={elapsed:.1f} timeoutSeconds={timeout_seconds} "
                    f"timestampUtc={utc_now()}\n"
                )
                log_handle.flush()
                next_heartbeat = time.monotonic() + heartbeat_seconds

            time.sleep(0.5)

        if reader_thread is not None:
            reader_thread.join(timeout=5)
        _drain_output_queue(output_queue, log_handle, output_lines)

        if return_code is None:
            return_code = process.poll()
        finished_at = utc_now()
        duration_seconds = round(time.monotonic() - monotonic_start, 3)
        log_handle.write(
            f"\nFinishedAtUtc: {finished_at}\n"
            f"DurationSeconds: {duration_seconds}\n"
            f"ExitCode: {return_code}\n"
            f"TimedOut: {timed_out}\n"
        )
        if timeout_at:
            log_handle.write(f"TimeoutAtUtc: {timeout_at}\n")
        if termination_method:
            log_handle.write(f"TerminationMethod: {termination_method}\n")

    tail_lines = output_lines[-output_tail_line_count:]
    if timed_out:
        status = "timed_out"
    else:
        status = "completed" if return_code == 0 else "failed"

    return {
        "printableCommand": printable,
        "logPath": log_path.as_posix(),
        "startedAtUtc": started_at,
        "finishedAtUtc": finished_at,
        "durationSeconds": round(time.monotonic() - monotonic_start, 3),
        "exitCode": return_code,
        "status": status,
        "timedOut": timed_out,
        "timeoutAtUtc": timeout_at,
        "timeoutSeconds": timeout_seconds,
        "heartbeatIntervalSeconds": heartbeat_seconds,
        "terminationMethod": termination_method,
        "stdinProvided": stdin_provided,
        "workingDirectory": working_directory_value,
        "outputTailLines": tail_lines,
    }


ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _sanitize_provider_log_line(line: str) -> str:
    return ANSI_ESCAPE_RE.sub("", line).replace("\r", "").strip()


def _read_text_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []


def _last_non_empty_lines(lines: List[str], limit: int) -> List[str]:
    selected: List[str] = []
    for line in reversed(lines):
        clean = _sanitize_provider_log_line(line)
        if clean:
            selected.append(clean)
        if len(selected) >= max(limit, 1):
            break
    return list(reversed(selected))


def _extract_provider_nodes(provider_config_path: Optional[Path]) -> List[Dict[str, Any]]:
    if provider_config_path is None or not provider_config_path.exists() or yaml is None:
        return []
    try:
        payload = yaml.safe_load(provider_config_path.read_text(encoding="utf-8-sig")) or {}
    except Exception:
        return []

    nodes: List[Dict[str, Any]] = []
    clusters = payload.get("clusters") if isinstance(payload, dict) else None
    if isinstance(clusters, list):
        for cluster in clusters:
            if not isinstance(cluster, dict):
                continue
            cluster_name = cluster.get("name")
            for role_key, role_name in (("control_plane", "control-plane"), ("workers", "worker")):
                for node in cluster.get(role_key) or []:
                    if not isinstance(node, dict):
                        continue
                    nodes.append({
                        "clusterName": cluster_name,
                        "role": role_name,
                        "name": node.get("name"),
                        "ipAddress": node.get("ip"),
                        "proxmoxNode": node.get("proxmox_node"),
                        "cores": node.get("cores"),
                        "memoryMiB": node.get("memory"),
                        "diskSizeGiB": node.get("disk_size"),
                    })
    elif isinstance(payload, dict):
        for role_key, role_name in (("control_plane", "control-plane"), ("workers", "worker")):
            for node in payload.get(role_key) or []:
                if not isinstance(node, dict):
                    continue
                nodes.append({
                    "clusterName": payload.get("cluster_name"),
                    "role": role_name,
                    "name": node.get("name"),
                    "ipAddress": node.get("ip"),
                    "proxmoxNode": node.get("proxmox_node"),
                    "cores": node.get("cores"),
                    "memoryMiB": node.get("memory"),
                    "diskSizeGiB": node.get("disk_size"),
                })
    return nodes


def _extract_provider_vmid_events(clean_lines: List[str]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    patterns = [
        re.compile(r"VMID\s+(?P<vmid>\d+)\s+is\s+no\s+longer\s+available.*?(?P<node>genai-[A-Za-z0-9_.-]+)?", re.IGNORECASE),
        re.compile(r"retrying\s+(?P<node>genai-[A-Za-z0-9_.-]+)\s+with\s+VMID\s+(?P<vmid>\d+)", re.IGNORECASE),
        re.compile(r"(?P<node>genai-[A-Za-z0-9_.-]+).*?VMID\s+(?P<vmid>\d+)", re.IGNORECASE),
    ]
    seen = set()
    for index, line in enumerate(clean_lines):
        if "vmid" not in line.lower():
            continue
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            item = {
                "lineIndex": index,
                "line": line[:500],
                "vmid": match.groupdict().get("vmid"),
                "node": match.groupdict().get("node"),
            }
            key = (item.get("lineIndex"), item.get("vmid"), item.get("node"), item.get("line"))
            if key not in seen:
                events.append(item)
                seen.add(key)
            break
    return events


def _infer_provider_phase(clean_lines: List[str]) -> Dict[str, Any]:
    phase_patterns = [
        ("provider_configuration", re.compile(r"Provider config|cluster create|Command:", re.IGNORECASE)),
        ("vm_allocation_or_clone", re.compile(r"VMID|clone|creating VM|created VM|starting VM|started VM", re.IGNORECASE)),
        ("control_plane_bootstrap", re.compile(r"Starting k3s$|waiting for k3s to be ready|k3s\.service", re.IGNORECASE)),
        ("worker_ssh_wait", re.compile(r"waiting for SSH on", re.IGNORECASE)),
        ("worker_agent_join", re.compile(r"joining agent .* to cluster|k3s-agent|Starting k3s-agent", re.IGNORECASE)),
        ("addon_installation", re.compile(r"addon|helm|monitoring|prometheus|istio|chaos|mentat|mon-agent", re.IGNORECASE)),
        ("kubeconfig_generation", re.compile(r"kubeconfig|writing kubeconfig|cluster kubeconfig", re.IGNORECASE)),
        ("provider_command_timeout", re.compile(r"ProviderCommandTimeout", re.IGNORECASE)),
    ]
    last_match: Optional[Dict[str, Any]] = None
    stage_hits: Dict[str, int] = {name: 0 for name, _ in phase_patterns}
    node_phase_hits: Dict[str, Dict[str, Any]] = {}
    node_pattern = re.compile(r"\[(?P<node>genai-[A-Za-z0-9_.-]+)\]")

    for index, line in enumerate(clean_lines):
        for stage, pattern in phase_patterns:
            if pattern.search(line):
                stage_hits[stage] += 1
                last_match = {"stage": stage, "lineIndex": index, "line": line[:500]}
        node_matches = [match.group("node") for match in node_pattern.finditer(line)]
        inline_specific_matches = re.findall(r"(genai-[A-Za-z0-9_-]+-(?:cp|worker)-[A-Za-z0-9_-]+)", line)
        specific_node_matches = [node for node in node_matches if re.search(r"-(cp|worker)-", node)] + inline_specific_matches
        node_name = (specific_node_matches or [None])[-1]
        if node_name:
            node_record = node_phase_hits.setdefault(node_name, {
                "node": node_name,
                "lastLineIndex": index,
                "lastLine": line[:500],
                "observedSignals": [],
            })
            node_record["lastLineIndex"] = index
            node_record["lastLine"] = line[:500]
            lowered = line.lower()
            for signal in [
                "downloading hash",
                "downloading binary",
                "installing k3s",
                "creating service file",
                "enabling k3s-agent",
                "starting k3s-agent",
                "starting k3s",
            ]:
                if signal in lowered and signal not in node_record["observedSignals"]:
                    node_record["observedSignals"].append(signal)

    inferred_stage = last_match["stage"] if last_match else "unknown"
    if inferred_stage == "provider_command_timeout":
        # Preserve the most useful pre-timeout phase instead of reporting only the wrapper timeout marker.
        for candidate in reversed(clean_lines):
            for stage, pattern in phase_patterns:
                if stage != "provider_command_timeout" and pattern.search(candidate):
                    inferred_stage = stage
                    break
            if inferred_stage != "provider_command_timeout":
                break

    return {
        "inferredBlockingStage": inferred_stage,
        "lastStageMatch": last_match,
        "stageHitCounts": stage_hits,
        "nodeLastSignals": sorted(node_phase_hits.values(), key=lambda item: item.get("node") or ""),
    }


def build_provider_command_diagnostics(
    *,
    result: Dict[str, Any],
    command: List[str],
    log_path: Path,
    diagnostics_root: Path,
    run_id: str,
    cycle_id: str,
    step_name: str,
    selected_config: Optional[Path],
    repo_root: Path,
    provider_config_kind: Optional[str],
) -> Dict[str, Any]:
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    raw_lines = _read_text_lines(log_path)
    clean_lines = [_sanitize_provider_log_line(line) for line in raw_lines]
    clean_lines = [line for line in clean_lines if line]
    phase = _infer_provider_phase(clean_lines)
    vmid_events = _extract_provider_vmid_events(clean_lines)
    provider_nodes = _extract_provider_nodes(selected_config)
    failure_class = "provider_command_timeout" if result.get("timedOut") else "provider_command_failure"
    if result.get("timedOut") and step_name == "create":
        failure_class = "provider_create_timeout"
    elif result.get("timedOut") and step_name == "delete":
        failure_class = "provider_delete_timeout"
    elif result.get("timedOut") and step_name == "kubeconfig":
        failure_class = "provider_kubeconfig_timeout"

    diagnostics_id = f"{run_id}_{step_name}_provider_diagnostics"
    diagnostics_json_path = diagnostics_root / f"{diagnostics_id}.json"
    diagnostics_text_path = diagnostics_root / f"{diagnostics_id}.txt"

    recommended_checks = []
    if result.get("timedOut") and step_name == "create":
        recommended_checks = [
            "Verify whether residual VMs for the same cluster name, VMID range, or IP allocation are still present in Proxmox before retrying.",
            "If the VMs still exist, inspect control-plane and worker systemd status for k3s and k3s-agent.",
            "Check worker connectivity to the control-plane Kubernetes API endpoint and SSH reachability between the provisioning host and each VM.",
            "Inspect provider-side logs for the worker that produced the last k3s-agent startup signal.",
            "Run the provider delete action with explicit confirmation before reusing the same cluster identity if the previous create timed out after VM creation.",
        ]

    payload = {
        "schemaVersion": "provider-command-diagnostics/v1",
        "diagnosticsId": diagnostics_id,
        "runId": run_id,
        "cycleId": cycle_id,
        "step": step_name,
        "status": "captured",
        "generatedAtUtc": utc_now(),
        "failureClass": failure_class,
        "command": command,
        "commandResult": {
            "status": result.get("status"),
            "exitCode": result.get("exitCode"),
            "timedOut": result.get("timedOut"),
            "timeoutSeconds": result.get("timeoutSeconds"),
            "durationSeconds": result.get("durationSeconds"),
            "terminationMethod": result.get("terminationMethod"),
            "timeoutAtUtc": result.get("timeoutAtUtc"),
        },
        "providerConfig": {
            "path": rel_or_abs(selected_config, repo_root),
            "kind": provider_config_kind,
        },
        "providerNodes": provider_nodes,
        "logAnalysis": {
            "logPath": rel_or_abs(log_path, repo_root),
            "lineCount": len(clean_lines),
            "inferredBlockingStage": phase.get("inferredBlockingStage"),
            "lastStageMatch": phase.get("lastStageMatch"),
            "stageHitCounts": phase.get("stageHitCounts"),
            "nodeLastSignals": phase.get("nodeLastSignals"),
            "vmidEvents": vmid_events,
            "tailLines": _last_non_empty_lines(raw_lines, 120),
        },
        "interpretation": {
            "summary": (
                "Provider create timed out before cluster validation. The provider log should be used to distinguish VM allocation, K3s server readiness, worker SSH wait, worker agent join, addon installation, or kubeconfig generation stalls."
                if result.get("timedOut") and step_name == "create"
                else "Provider command failed or timed out before the next pipeline phase."
            ),
            "notApplicationLevel": step_name in {"create", "kubeconfig", "delete"},
            "nextPipelinePhaseBlocked": "cluster_validation" if step_name == "create" else None,
            "recommendedOperatorChecks": recommended_checks,
        },
        "artifacts": {
            "diagnosticsJsonPath": rel_or_abs(diagnostics_json_path, repo_root),
            "diagnosticsTextPath": rel_or_abs(diagnostics_text_path, repo_root),
        },
    }

    write_json(diagnostics_json_path, payload)

    lines = [
        "Provider command diagnostics",
        "============================",
        "",
        f"Run ID: {run_id}",
        f"Step: {step_name}",
        f"Failure class: {failure_class}",
        f"Command status: {result.get('status')}",
        f"Exit code: {result.get('exitCode')}",
        f"Timed out: {result.get('timedOut')}",
        f"Timeout seconds: {result.get('timeoutSeconds')}",
        f"Duration seconds: {result.get('durationSeconds')}",
        f"Termination method: {result.get('terminationMethod')}",
        f"Provider config: {rel_or_abs(selected_config, repo_root)}",
        f"Log path: {rel_or_abs(log_path, repo_root)}",
        "",
        "Log analysis:",
        f"- Inferred blocking stage: {phase.get('inferredBlockingStage')}",
        f"- VMID-related events: {len(vmid_events)}",
        f"- Provider nodes discovered from config: {len(provider_nodes)}",
    ]
    if phase.get("nodeLastSignals"):
        lines.append("- Node last signals:")
        for item in phase.get("nodeLastSignals") or []:
            lines.append(
                f"  - {item.get('node')}: {', '.join(item.get('observedSignals') or []) or 'no classified signal'}; "
                f"last='{item.get('lastLine')}'"
            )
    if vmid_events:
        lines.append("- VMID events:")
        for event in vmid_events:
            lines.append(f"  - VMID={event.get('vmid')} node={event.get('node')} line='{event.get('line')}'")
    if recommended_checks:
        lines.append("")
        lines.append("Recommended operator checks:")
        for item in recommended_checks:
            lines.append(f"- {item}")
    lines.append("")
    lines.append("Provider output tail:")
    for line in payload["logAnalysis"]["tailLines"][-40:]:
        lines.append(f"- {line}")
    write_text(diagnostics_text_path, "\n".join(lines) + "\n")

    return {
        "status": "captured",
        "failureClass": failure_class,
        "inferredBlockingStage": phase.get("inferredBlockingStage"),
        "diagnosticsJsonPath": diagnostics_json_path.as_posix(),
        "diagnosticsTextPath": diagnostics_text_path.as_posix(),
        "vmidEventCount": len(vmid_events),
        "providerNodeCount": len(provider_nodes),
    }


def _sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None


def _first_non_empty_line(text: str) -> Optional[str]:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:240]
    return None


def _server_hosts_from_kubeconfig(config: Dict[str, Any]) -> List[str]:
    hosts: List[str] = []
    for item in config.get("clusters") or []:
        if not isinstance(item, dict):
            continue
        cluster = item.get("cluster") or {}
        if not isinstance(cluster, dict):
            continue
        server = cluster.get("server")
        if isinstance(server, str) and server.strip():
            hosts.append(server.strip())
    return hosts


def validate_kubeconfig_structure(path: Optional[Path], repo_root: Path, expected_cluster_name: Optional[str] = None) -> Dict[str, Any]:
    exists = bool(path and path.exists())
    file_size = path.stat().st_size if exists and path else 0
    non_empty = file_size > 0

    result: Dict[str, Any] = {
        "exists": exists,
        "nonEmpty": non_empty,
        "fileSizeBytes": file_size,
        "sha256": _sha256_file(path) if exists and path else None,
        "yamlParseStatus": "not_attempted",
        "structuralStatus": "not_attempted",
        "serverEndpoints": [],
        "checks": [],
        "errors": [],
        "warnings": [],
    }

    if not exists:
        result["yamlParseStatus"] = "skipped_missing_file"
        result["structuralStatus"] = "failed_missing_file"
        result["errors"].append("kubeconfig_file_missing")
        return result
    if not non_empty:
        result["yamlParseStatus"] = "skipped_empty_file"
        result["structuralStatus"] = "failed_empty_file"
        result["errors"].append("kubeconfig_file_empty")
        return result

    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        result["yamlParseStatus"] = "failed_unreadable"
        result["structuralStatus"] = "failed_unreadable"
        result["errors"].append("kubeconfig_file_unreadable")
        result["readError"] = str(exc)
        return result

    result["firstNonEmptyLine"] = _first_non_empty_line(text)

    if yaml is None:
        result["yamlParseStatus"] = "skipped_missing_pyyaml"
        result["structuralStatus"] = "not_enforced_missing_pyyaml"
        result["warnings"].append("pyyaml_not_available_for_kubeconfig_structure_validation")
        return result

    try:
        parsed = yaml.safe_load(text)
        result["yamlParseStatus"] = "parsed"
    except Exception as exc:
        result["yamlParseStatus"] = "failed_malformed_yaml"
        result["structuralStatus"] = "failed_malformed_yaml"
        result["errors"].append("kubeconfig_yaml_parse_failed")
        result["parseError"] = str(exc)
        return result

    if not isinstance(parsed, dict):
        result["structuralStatus"] = "failed_invalid_document_type"
        result["errors"].append("kubeconfig_document_is_not_mapping")
        return result

    required_top_level = ["apiVersion", "kind", "clusters", "contexts", "current-context", "users"]
    for key in required_top_level:
        present = key in parsed
        result["checks"].append({"name": f"top_level_{key}", "passed": present})
        if not present:
            result["errors"].append(f"missing_top_level_{key}")

    if parsed.get("kind") != "Config":
        result["warnings"].append("kubeconfig_kind_is_not_Config")
    if parsed.get("apiVersion") != "v1":
        result["warnings"].append("kubeconfig_apiVersion_is_not_v1")

    clusters = parsed.get("clusters")
    contexts = parsed.get("contexts")
    users = parsed.get("users")
    for key, value in (("clusters", clusters), ("contexts", contexts), ("users", users)):
        is_non_empty_list = isinstance(value, list) and len(value) > 0
        result["checks"].append({"name": f"{key}_non_empty_list", "passed": is_non_empty_list})
        if not is_non_empty_list:
            result["errors"].append(f"{key}_missing_or_empty")

    cluster_names = [item.get("name") for item in clusters or [] if isinstance(item, dict)]
    context_names = [item.get("name") for item in contexts or [] if isinstance(item, dict)]
    user_names = [item.get("name") for item in users or [] if isinstance(item, dict)]
    result["clusterNames"] = [name for name in cluster_names if isinstance(name, str)]
    result["contextNames"] = [name for name in context_names if isinstance(name, str)]
    result["userNames"] = [name for name in user_names if isinstance(name, str)]
    result["serverEndpoints"] = _server_hosts_from_kubeconfig(parsed)

    if expected_cluster_name:
        expected_seen = expected_cluster_name in result["clusterNames"] and expected_cluster_name in result["contextNames"] and expected_cluster_name in result["userNames"]
        result["checks"].append({"name": "expected_cluster_identity_present", "passed": expected_seen, "expectedClusterName": expected_cluster_name})
        if not expected_seen:
            result["warnings"].append("expected_cluster_identity_not_found_in_all_sections")

    has_https_server = any(str(server).startswith("https://") for server in result["serverEndpoints"])
    result["checks"].append({"name": "cluster_server_endpoint_https", "passed": has_https_server})
    if not has_https_server:
        result["errors"].append("missing_https_cluster_server_endpoint")

    result["structuralStatus"] = "valid" if not result["errors"] else "failed_invalid_structure"
    return result


def kubeconfig_status_from_structure(structure: Dict[str, Any], dry_run: bool) -> str:
    if dry_run:
        return "not_enforced_dry_run"
    if not structure.get("exists"):
        return "failed_missing_file"
    if not structure.get("nonEmpty"):
        return "failed_empty_file"
    if structure.get("yamlParseStatus") == "failed_malformed_yaml":
        return "failed_malformed_yaml"
    if structure.get("structuralStatus") == "failed_invalid_structure":
        return "failed_invalid_structure"
    if structure.get("structuralStatus") == "valid":
        return "verified"
    if structure.get("structuralStatus") == "not_enforced_missing_pyyaml":
        return "verified_without_structural_validation"
    return "failed_unclassified_kubeconfig_validation"


def verify_kubeconfig(repo_root: Path, binding: Dict[str, Any], provisioning_profile: Dict[str, Any], dry_run: bool, selected_config: Optional[Path] = None) -> Dict[str, Any]:
    expected = expected_kubeconfig_value(binding, provisioning_profile, selected_config)
    expected_path = repo_path(repo_root, expected)
    selected_identity = parse_provider_config_identity(selected_config)
    expected_cluster_name = selected_identity.get("clusterName") or expected_binding_identity(binding).get("clusterName")
    structure = validate_kubeconfig_structure(expected_path, repo_root, expected_cluster_name=expected_cluster_name)
    status = kubeconfig_status_from_structure(structure, dry_run)

    return {
        "expectedPath": expected,
        "resolvedPath": rel_or_abs(expected_path, repo_root),
        "exists": structure.get("exists"),
        "nonEmpty": structure.get("nonEmpty"),
        "status": status,
        "structureValidation": structure,
    }


def backup_invalid_kubeconfig(kubeconfig_path: Optional[Path], diagnostics_root: Path, run_id: str, label: str, repo_root: Path) -> Dict[str, Any]:
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    exists = bool(kubeconfig_path and kubeconfig_path.exists())
    backup_path = diagnostics_root / f"{run_id}_{label}.invalid-kubeconfig"
    result: Dict[str, Any] = {
        "label": label,
        "sourcePath": rel_or_abs(kubeconfig_path, repo_root),
        "exists": exists,
        "backupPath": rel_or_abs(backup_path, repo_root),
        "status": "not_required_missing_source" if not exists else "pending",
    }
    if exists and kubeconfig_path:
        try:
            shutil.copy2(kubeconfig_path, backup_path)
            result["status"] = "backed_up"
            result["fileSizeBytes"] = backup_path.stat().st_size
            result["sha256"] = _sha256_file(backup_path)
        except Exception as exc:
            result["status"] = "backup_failed"
            result["error"] = str(exc)
    return result


def build_text_summary(manifest: Dict[str, Any]) -> str:
    lines = [
        "Provider-backed provisioning integration summary",
        "================================================",
        "",
        f"Run ID: {manifest.get('runId')}",
        f"Status: {manifest.get('status')}",
        f"Action: {manifest.get('action')}",
        f"Cycle: {manifest.get('cycle', {}).get('cycleId')}",
        f"Infrastructure profile: {manifest.get('infrastructure', {}).get('infrastructureProfileId')}",
        f"Provider: {manifest.get('provider', {}).get('providerId')}",
        f"Provider binding: {manifest.get('providerBinding', {}).get('providerBindingId')}",
        f"Cluster lifecycle mode: {manifest.get('clusterLifecycle', {}).get('clusterLifecycleMode')}",
        f"Destroy cluster after cycle: {manifest.get('clusterLifecycle', {}).get('destroyClusterAfterCycle')}",
        f"Provider config: {manifest.get('providerConfig', {}).get('resolvedPath')}",
        f"Provider config status: {manifest.get('providerConfig', {}).get('status')}",
        "",
        "Command plan:",
    ]
    command_plan = manifest.get("commandPlan") or {}
    if command_plan:
        lines.append(f"- Kubeconfig handling: {command_plan.get('kubeconfigHandling')}")
        planned_steps = command_plan.get("steps") or []
        if planned_steps:
            lines.append("- Steps: " + ", ".join(str(item.get("step")) for item in planned_steps))
        for note in command_plan.get("notes") or []:
            lines.append(f"- Note: {note}")

    lines.extend([
        "",
        "Command results:",
    ])
    for result in manifest.get("commandResults", []):
        timeout_detail = ""
        if result.get("timedOut"):
            timeout_detail = f", timeoutSeconds={result.get('timeoutSeconds')}"
        lines.append(
            f"- {result.get('step')}: {result.get('status')} "
            f"(exitCode={result.get('exitCode')}{timeout_detail}, log={result.get('logPath')})"
        )
        diagnostics = result.get("providerDiagnostics") or {}
        if diagnostics:
            lines.append(
                "  Provider diagnostics: "
                f"{diagnostics.get('failureClass')} "
                f"(stage={diagnostics.get('inferredBlockingStage')}, "
                f"json={diagnostics.get('diagnosticsJsonPath')})"
            )
        if result.get("status") in {"failed", "timed_out"} and result.get("outputTailLines"):
            lines.append("  Provider output tail:")
            for line in result.get("outputTailLines", [])[-20:]:
                lines.append(f"  - {line}")
    kube = manifest.get("kubeconfigVerification")
    if kube:
        structure = kube.get("structureValidation") or {}
        lines.extend([
            "",
            "Kubeconfig verification:",
            f"- Path: {kube.get('resolvedPath')}",
            f"- Status: {kube.get('status')}",
            f"- Exists: {kube.get('exists')}",
            f"- Non-empty: {kube.get('nonEmpty')}",
            f"- YAML parse status: {structure.get('yamlParseStatus')}",
            f"- Structural status: {structure.get('structuralStatus')}",
        ])
        if structure.get("serverEndpoints"):
            lines.append("- Server endpoints: " + ", ".join(str(item) for item in structure.get("serverEndpoints")))
        if structure.get("errors"):
            lines.append("- Structural errors: " + ", ".join(str(item) for item in structure.get("errors")))
    repair_attempts = manifest.get("kubeconfigRepairAttempts") or []
    if repair_attempts:
        lines.append("")
        lines.append("Kubeconfig repair attempts:")
        for attempt in repair_attempts:
            lines.append(
                f"- Attempt {attempt.get('attempt')}: {attempt.get('status')} "
                f"(trigger={attempt.get('triggerStatus')}, "
                f"postStatus={(attempt.get('postRefreshVerification') or {}).get('status')})"
            )
    if manifest.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for warning in manifest["warnings"]:
            lines.append(f"- {warning}")
    if manifest.get("errors"):
        lines.append("")
        lines.append("Errors:")
        for error in manifest["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run provider-backed provisioning integration.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C1.json")
    parser.add_argument("--provisioning-profile", default=None)
    parser.add_argument("--action", choices=sorted(VALID_ACTIONS), default="provision")
    parser.add_argument("--tool-path", default="proxmox-k3s")
    parser.add_argument("--provider-config", default=None)
    parser.add_argument("--cluster-lifecycle-mode", choices=["reuse", "ephemeral", "external"], default=None)
    parser.add_argument("--destroy-cluster-after-cycle", choices=["true", "false"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-delete", action="store_true")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else default_repo_root()
    run_id = args.run_id or f"provider_provisioning_{args.action}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    started_at = utc_now()

    errors: List[str] = []
    warnings: List[str] = []
    command_results: List[Dict[str, Any]] = []
    kubeconfig_result: Optional[Dict[str, Any]] = None
    kubeconfig_repair_attempts: List[Dict[str, Any]] = []
    kubeconfig_directory_preparation: Optional[Dict[str, Any]] = None

    try:
        cycle_path, cycle = load_cycle(repo_root, args.cycle_config)
        infra_path, infra_profile = resolve_infrastructure_profile(repo_root, cycle)
        binding_path, binding = resolve_provider_binding(repo_root, cycle, infra_profile)
        lifecycle_path, lifecycle_policy = resolve_lifecycle_policy(repo_root, cycle, binding)
        provisioning_profile_path, provisioning_profile = resolve_provisioning_profile(repo_root, cycle, args.provisioning_profile)

        cycle_id = cycle.get("cycleId", "UNKNOWN")
        provider_backed = cycle.get("providerBackedInfrastructure", {})
        cluster_lifecycle = cycle.get("clusterLifecycle", {})

        mode = args.cluster_lifecycle_mode or cluster_lifecycle.get("clusterLifecycleMode") or provider_backed.get("clusterLifecycleMode") or binding.get("clusterLifecycle", {}).get("clusterLifecycleModeDefault") or "reuse"
        destroy_override = bool_from_optional(args.destroy_cluster_after_cycle)
        destroy_after_cycle = destroy_override if destroy_override is not None else bool(cluster_lifecycle.get("destroyClusterAfterCycle", provider_backed.get("destroyClusterAfterCycle", binding.get("clusterLifecycle", {}).get("destroyClusterAfterCycleDefault", False))))

        selected_config, selected_key, candidates, provider_config_resolution_context = resolve_provider_config(
            repo_root=repo_root,
            binding=binding,
            provisioning_profile=provisioning_profile,
            action=args.action,
            dry_run=args.dry_run,
            override=args.provider_config,
        )

        artifact_policy = provisioning_profile.get("artifactPolicy", {})
        output_root_override_applied = bool(args.output_root and str(args.output_root).strip())
        output_root_value = (
            str(args.output_root).strip()
            if output_root_override_applied
            else artifact_policy.get("root") or provider_backed.get("provisioningLogRoot") or f"results/experimental-cycles/{cycle_id}/infrastructure/provisioning"
        )
        output_root = repo_path(repo_root, output_root_value.format(cycleId=cycle_id)) or repo_root / "results" / "provisioning"

        if output_root_override_applied:
            logs_root = output_root / "logs"
            manifests_root = output_root / "manifests"
            commands_root = output_root / "commands"
        else:
            logs_root_value = artifact_policy.get("logsRoot")
            manifests_root_value = artifact_policy.get("manifestsRoot")
            commands_root_value = artifact_policy.get("commandsRoot")
            logs_root = repo_path(repo_root, logs_root_value.format(cycleId=cycle_id)) if logs_root_value else (output_root / "logs")
            manifests_root = repo_path(repo_root, manifests_root_value.format(cycleId=cycle_id)) if manifests_root_value else (output_root / "manifests")
            commands_root = repo_path(repo_root, commands_root_value.format(cycleId=cycle_id)) if commands_root_value else (output_root / "commands")

        kubeconfig_diagnostics_root = output_root / "kubeconfig-diagnostics"
        provider_failure_diagnostics_policy = (provisioning_profile.get("providerCommandExecution") or {}).get("failureDiagnostics") or {}
        provider_diagnostics_root_value = provider_failure_diagnostics_policy.get("diagnosticsRoot")
        provider_diagnostics_root = (
            repo_path(repo_root, str(provider_diagnostics_root_value).format(cycleId=cycle_id))
            if provider_diagnostics_root_value
            else (output_root / "provider-diagnostics")
        )
        if provider_diagnostics_root is None:
            provider_diagnostics_root = output_root / "provider-diagnostics"

        for directory in [output_root, logs_root, manifests_root, commands_root, kubeconfig_diagnostics_root, provider_diagnostics_root]:
            directory.mkdir(parents=True, exist_ok=True)

        requires_real_config = args.action in {"provision", "kubeconfig", "destroy"} and not args.dry_run
        selected_config_exists = bool(selected_config and selected_config.exists())
        selected_config_kind = provider_config_resolution_context.get("selectedProviderConfigKind")
        real_execution_config_available = bool(
            selected_config_exists
            and selected_config_kind not in {"examplePath", "templatePath", "unresolved"}
        )
        resolved_tool_path, tool_resolution = resolve_provider_tool(repo_root, args.tool_path)
        lifecycle_collision_guard, guard_warnings, guard_errors = build_lifecycle_collision_guard(
            repo_root=repo_root,
            selected_config=selected_config,
            binding=binding,
            provisioning_profile=provisioning_profile,
            mode=mode,
            action=args.action,
        )
        warnings.extend(guard_warnings)
        errors.extend(guard_errors)

        if requires_real_config and not real_execution_config_available:
            errors.append("No local provider configuration file is available for real provider execution.")
        if requires_real_config and not resolved_tool_path:
            errors.append(tool_resolution.get("hint") or f"Provider executable not found: {args.tool_path}")
        if args.action == "destroy" and not args.dry_run and not args.confirm_delete:
            errors.append("Cluster deletion requires explicit confirmation.")
        if mode == "external" and args.action in {"provision", "destroy"}:
            errors.append("Provider create/delete commands are not allowed for external lifecycle mode.")

        if real_execution_config_available:
            provider_status = "resolved_for_real_execution"
        elif selected_config_exists and not requires_real_config:
            provider_status = "resolved_for_review_or_dry_run"
        elif selected_config_exists:
            provider_status = "resolved_but_not_allowed_for_real_execution"
        else:
            provider_status = "unresolved"

        if not errors and args.action in {"provision", "kubeconfig"}:
            kubeconfig_directory_preparation = prepare_kubeconfig_parent_directory(
                repo_root=repo_root,
                binding=binding,
                provisioning_profile=provisioning_profile,
                selected_config=selected_config,
                action=args.action,
                dry_run=args.dry_run,
            )
            if (
                not args.dry_run
                and kubeconfig_directory_preparation.get("required")
                and kubeconfig_directory_preparation.get("status") != "ready"
            ):
                errors.append(
                    "Kubeconfig parent directory preparation failed: "
                    f"{kubeconfig_directory_preparation.get('status')}"
                )

        command_plan: Dict[str, Any] = {
            "action": args.action,
            "steps": [],
            "kubeconfigHandling": "not_applicable",
            "notes": [],
        }

        if not errors and args.action != "plan":
            steps: List[Tuple[str, str]] = []
            if args.action == "provision":
                steps = [("create", "01_create")]
                command_plan["kubeconfigHandling"] = "created_by_cluster_create_then_structurally_verified_with_optional_refresh"
                command_plan["notes"].append(
                    "The provision action verifies the kubeconfig as a readable Kubernetes config and refreshes it with proxmox-k3s cluster kubeconfig when the created file is malformed or structurally invalid."
                )
            elif args.action == "kubeconfig":
                steps = [("kubeconfig", "01_kubeconfig")]
                command_plan["kubeconfigHandling"] = "explicit_refresh_command"
                command_plan["notes"].append(
                    "The kubeconfig action explicitly invokes proxmox-k3s cluster kubeconfig to refresh an existing cluster kubeconfig."
                )
            elif args.action == "destroy":
                steps = [("delete", "01_delete")]
                command_plan["kubeconfigHandling"] = "not_required"

            command_plan["steps"] = [
                {"step": step_name, "artifactPrefix": step_prefix}
                for step_name, step_prefix in steps
            ]

            provider_command_execution_policy = provisioning_profile.get("providerCommandExecution") or {}
            command_plan["executionPolicy"] = {
                "mode": provider_command_execution_policy.get("mode") or "streamed_with_timeout",
                "defaultTimeoutSeconds": _coerce_positive_int(provider_command_execution_policy.get("defaultTimeoutSeconds"), 3600),
                "perStepTimeoutSeconds": provider_command_execution_policy.get("perStepTimeoutSeconds") or {},
                "heartbeatIntervalSeconds": _coerce_positive_int(provider_command_execution_policy.get("heartbeatIntervalSeconds"), 60),
                "gracefulTerminationSeconds": _coerce_positive_int(provider_command_execution_policy.get("gracefulTerminationSeconds"), 30),
                "outputTailLines": _coerce_positive_int(provider_command_execution_policy.get("outputTailLines"), 80),
                "failureDiagnostics": provider_command_execution_policy.get("failureDiagnostics") or {"enabled": True},
            }

            if selected_config is None:
                errors.append("Provider configuration could not be resolved.")
            else:
                def execute_provider_step(step_name: str, step_prefix: str) -> Dict[str, Any]:
                    command = command_for(step_name, resolved_tool_path or args.tool_path, selected_config, args.confirm_delete)
                    log_path = logs_root / f"{run_id}_{step_prefix}.log"
                    stdin_text = "y\n" if step_name == "delete" and args.confirm_delete else None
                    result = run_command(
                        command,
                        log_path,
                        args.dry_run,
                        stdin_text=stdin_text,
                        working_directory=repo_root,
                        execution_policy=provider_command_execution_policy,
                        step_name=step_name,
                    )
                    result["step"] = step_name
                    diagnostics_policy = provider_command_execution_policy.get("failureDiagnostics") or {}
                    diagnostics_enabled = bool(diagnostics_policy.get("enabled", True))
                    if diagnostics_enabled and result.get("status") in {"failed", "timed_out"}:
                        result["providerDiagnostics"] = build_provider_command_diagnostics(
                            result=result,
                            command=command,
                            log_path=log_path,
                            diagnostics_root=provider_diagnostics_root,
                            run_id=run_id,
                            cycle_id=cycle_id,
                            step_name=step_name,
                            selected_config=selected_config,
                            repo_root=repo_root,
                            provider_config_kind=selected_config_kind,
                        )
                    result["commandManifestPath"] = (commands_root / f"{run_id}_{step_prefix}.command-manifest.json").as_posix()
                    write_json(Path(result["commandManifestPath"]), {
                        "schemaVersion": "provider-command-result/v1",
                        "runId": run_id,
                        "cycleId": cycle_id,
                        "step": step_name,
                        "command": command,
                        "result": result,
                    })
                    command_results.append(result)
                    return result

                for step_name, step_prefix in steps:
                    result = execute_provider_step(step_name, step_prefix)
                    if result.get("timedOut"):
                        errors.append(f"Provider command timed out: {step_name}")
                        break
                    if result["exitCode"] != 0:
                        errors.append(f"Provider command failed: {step_name}")
                        break

                if args.action in {"provision", "kubeconfig"} and not errors:
                    kubeconfig_result = verify_kubeconfig(repo_root, binding, provisioning_profile, args.dry_run, selected_config)
                    successful_statuses = {"verified", "verified_without_structural_validation"}
                    kubeconfig_policy = provisioning_profile.get("kubeconfigVerification") or {}
                    refresh_policy = str(kubeconfig_policy.get("refreshAfterCreatePolicy") or kubeconfig_policy.get("refreshOnInvalidPolicy") or "when_invalid")
                    max_refresh_attempts = int(kubeconfig_policy.get("maxRefreshAttemptsAfterInvalid") or 1)
                    expected_kubeconfig_path = repo_path(repo_root, kubeconfig_result.get("expectedPath"))

                    should_try_refresh = (
                        not args.dry_run
                        and args.action in {"provision", "kubeconfig"}
                        and kubeconfig_result.get("status") not in successful_statuses
                        and refresh_policy in {"when_invalid", "always"}
                        and max_refresh_attempts > 0
                    )

                    refresh_attempt = 0
                    while should_try_refresh and refresh_attempt < max_refresh_attempts and kubeconfig_result.get("status") not in successful_statuses:
                        refresh_attempt += 1
                        refresh_step_prefix = f"{refresh_attempt + len(steps):02d}_kubeconfig_refresh_after_failed_verification"
                        command_plan.setdefault("steps", []).append({
                            "step": "kubeconfig",
                            "artifactPrefix": refresh_step_prefix,
                            "trigger": "invalid_kubeconfig_verification",
                            "attempt": refresh_attempt,
                        })
                        backup = backup_invalid_kubeconfig(
                            expected_kubeconfig_path,
                            kubeconfig_diagnostics_root,
                            run_id,
                            f"before_refresh_attempt_{refresh_attempt}",
                            repo_root,
                        )
                        refresh_result = execute_provider_step("kubeconfig", refresh_step_prefix)
                        post_refresh_verification = verify_kubeconfig(repo_root, binding, provisioning_profile, args.dry_run, selected_config)
                        repair_record = {
                            "attempt": refresh_attempt,
                            "triggerStatus": kubeconfig_result.get("status"),
                            "backup": backup,
                            "refreshCommandResult": refresh_result,
                            "postRefreshVerification": post_refresh_verification,
                            "status": "repaired" if post_refresh_verification.get("status") in successful_statuses else "still_invalid",
                        }
                        kubeconfig_repair_attempts.append(repair_record)
                        kubeconfig_result = post_refresh_verification
                        if refresh_result.get("timedOut"):
                            errors.append("Provider kubeconfig refresh command timed out after invalid kubeconfig verification.")
                            break
                        if refresh_result.get("exitCode") != 0:
                            errors.append("Provider kubeconfig refresh command failed after invalid kubeconfig verification.")
                            break

                    if not args.dry_run and kubeconfig_result.get("status") not in successful_statuses and not errors:
                        errors.append(f"Kubeconfig verification failed: {kubeconfig_result.get('status')}")

        elif args.action == "plan":
            command_plan = {
                "action": args.action,
                "steps": [],
                "kubeconfigHandling": "not_applicable",
                "notes": ["Plan action resolves provider configuration and lifecycle metadata without executing provider commands."],
            }

        finished_at = utc_now()
        status = "completed" if not errors and not args.dry_run else ("dry_run" if args.dry_run and not errors else "failed")
        if args.action == "plan" and not errors:
            status = "planned"

        manifest_path = manifests_root / f"{run_id}.provisioning-integration-manifest.json"
        text_summary_path = manifests_root / f"{run_id}.provisioning-integration-summary.txt"

        manifest = {
            "schemaVersion": "provider-backed-provisioning-integration-manifest/v1",
            "runId": run_id,
            "action": args.action,
            "status": status,
            "startedAtUtc": started_at,
            "finishedAtUtc": finished_at,
            "dryRun": args.dry_run,
            "cycle": {
                "cycleId": cycle_id,
                "cycleName": cycle.get("cycleName"),
                "cycleConfigPath": rel_or_abs(cycle_path, repo_root),
            },
            "provisioningIntegrationProfile": {
                "profileId": provisioning_profile.get("provisioningIntegrationProfileId"),
                "profilePath": rel_or_abs(provisioning_profile_path, repo_root),
            },
            "infrastructure": {
                "infrastructureProfileId": provider_backed.get("infrastructureProfileId") or infra_profile.get("infrastructureProfileId"),
                "infrastructureProfilePath": rel_or_abs(infra_path, repo_root),
                "clusterName": infra_profile.get("clusterIdentity", {}).get("clusterName"),
            },
            "provider": {
                "providerId": provider_backed.get("provider") or binding.get("providerId"),
                "toolPath": args.tool_path,
                "toolResolution": tool_resolution,
            },
            "providerBinding": {
                "providerBindingId": binding.get("providerBindingId"),
                "providerBindingPath": rel_or_abs(binding_path, repo_root),
            },
            "providerConfig": {
                "status": provider_status,
                "selectedKey": selected_key,
                "resolvedPath": rel_or_abs(selected_config, repo_root),
                "resolutionContext": provider_config_resolution_context,
                "candidates": candidates,
                "overrideRequested": bool(args.provider_config),
                "realExecutionConfigAvailable": real_execution_config_available,
            },
            "clusterLifecycle": {
                "clusterLifecycleMode": mode,
                "destroyClusterAfterCycle": destroy_after_cycle,
                "lifecyclePolicyId": lifecycle_policy.get("lifecyclePolicyId") or cluster_lifecycle.get("lifecyclePolicyId"),
                "lifecyclePolicyPath": rel_or_abs(lifecycle_path, repo_root),
                "deleteRequiresExplicitConfirmation": lifecycle_policy.get("executionGuards", {}).get("requireExplicitDeleteConfirmation", True),
            },
            "artifacts": {
                "outputRoot": rel_or_abs(output_root, repo_root),
                "outputRootOverrideApplied": output_root_override_applied,
                "logsRoot": rel_or_abs(logs_root, repo_root),
                "manifestsRoot": rel_or_abs(manifests_root, repo_root),
                "commandsRoot": rel_or_abs(commands_root, repo_root),
                "kubeconfigDiagnosticsRoot": rel_or_abs(kubeconfig_diagnostics_root, repo_root),
                "providerDiagnosticsRoot": rel_or_abs(provider_diagnostics_root, repo_root),
                "manifestPath": rel_or_abs(manifest_path, repo_root),
                "textSummaryPath": rel_or_abs(text_summary_path, repo_root),
            },
            "commandPlan": command_plan,
            "commandResults": command_results,
            "kubeconfigDirectoryPreparation": kubeconfig_directory_preparation,
            "kubeconfigVerification": kubeconfig_result,
            "kubeconfigRepairAttempts": kubeconfig_repair_attempts,
            "lifecycleCollisionGuard": lifecycle_collision_guard,
            "warnings": warnings,
            "errors": errors,
            "decision": {
                "canProceedToClusterValidation": status in {"completed", "dry_run", "planned"} and not errors and (args.dry_run or args.action == "plan" or args.action in {"provision", "kubeconfig"}),
                "canProceedToApplicationDeployment": status == "completed" and args.action in {"provision", "kubeconfig"} and not errors,
                "stopBeforeApplicationDeployment": bool(errors),
            },
        }

        write_json(manifest_path, manifest)
        write_text(text_summary_path, build_text_summary(manifest))

        write_latest = args.write_latest_aliases or bool(artifact_policy.get("writeLatestAliases"))
        if write_latest:
            if output_root_override_applied:
                latest_manifest = output_root / "latest-provisioning-integration-manifest.json"
                latest_text = output_root / "latest-provisioning-integration-summary.txt"
            else:
                latest_manifest_value = artifact_policy.get("latestManifestPath") or (output_root.as_posix() + "/latest-provisioning-integration-manifest.json")
                latest_text_value = artifact_policy.get("latestTextSummaryPath") or (output_root.as_posix() + "/latest-provisioning-integration-summary.txt")
                latest_manifest = repo_path(repo_root, latest_manifest_value.format(cycleId=cycle_id))
                latest_text = repo_path(repo_root, latest_text_value.format(cycleId=cycle_id))
            if latest_manifest:
                write_json(latest_manifest, manifest)
            if latest_text:
                write_text(latest_text, build_text_summary(manifest))

        print(f"Provisioning integration status: {status}")
        print(f"Manifest: {manifest_path}")
        print(f"Summary: {text_summary_path}")
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        return 0

    except Exception as exc:
        fallback_root = repo_root / "results" / "_runtime" / "provisioning-integration-failures"
        fallback_root.mkdir(parents=True, exist_ok=True)
        failure_path = fallback_root / f"{run_id}.failure.json"
        write_json(failure_path, {
            "schemaVersion": "provider-backed-provisioning-integration-failure/v1",
            "runId": run_id,
            "action": args.action,
            "status": "failed",
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "error": str(exc),
        })
        print(f"Provisioning integration failed before cycle-scoped artifact resolution: {exc}", file=sys.stderr)
        print(f"Failure artifact: {failure_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
