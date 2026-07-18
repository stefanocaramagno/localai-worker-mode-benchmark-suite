#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

DEFAULT_PROFILE = "config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json"
DEFAULT_ACTION = "install"


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
    return (lambda payload, _path: payload), (lambda text, _path: text)


normalize_artifact_payload_for_output, normalize_artifact_text_for_output = _load_artifact_path_helpers()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_repo_root(value: Optional[str]) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def repo_path(repo_root: Path, value: Optional[str], default: Optional[str] = None) -> Optional[Path]:
    raw = value if value not in (None, "") else default
    if raw in (None, ""):
        return None
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def nested_get(value: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def repo_relative(repo_root: Path, path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix().replace("\\", "/")


def experimental_cycle_id_from_path(repo_root: Path, path: Optional[Path]) -> Optional[str]:
    rel = repo_relative(repo_root, path)
    if not rel:
        return None
    parts = rel.split("/")
    for index, part in enumerate(parts[:-1]):
        if part == "experimental-cycles" and index + 1 < len(parts):
            return parts[index + 1]
    return None


def latest_alias_target_error(repo_root: Path, artifact_root: Path, latest_path: Optional[Path], label: str) -> Optional[str]:
    if latest_path is None:
        return None
    artifact_cycle = experimental_cycle_id_from_path(repo_root, artifact_root)
    latest_cycle = experimental_cycle_id_from_path(repo_root, latest_path)
    if artifact_cycle and latest_cycle and artifact_cycle != latest_cycle:
        return (
            f"refusing_to_write_{label.replace(' ', '_')}: "
            f"artifactRootCycle={artifact_cycle}, latestAliasCycle={latest_cycle}, "
            f"latestAliasPath={repo_relative(repo_root, latest_path)}"
        )
    return None


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to validate scheduler-plugins Helm chart metadata.")
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dotted_get(value: Dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    current: Any = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def write_json(path: Path, payload: Any, repo_root: Optional[Path] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def run_command(command: List[str], timeout: Optional[int] = None, stdin: Optional[str] = None) -> Dict[str, Any]:
    started_at = utc_now()
    try:
        completed = subprocess.run(command, input=stdin, text=True, capture_output=True, timeout=timeout)
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "exitCode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "success": completed.returncode == 0,
        }
    except Exception as exc:
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "exitCode": 1,
            "stdout": "",
            "stderr": str(exc),
            "success": False,
        }


def command_result_summary(result: Dict[str, Any], output_path: Optional[Path] = None, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    summary = {
        "command": result.get("command") or [],
        "startedAtUtc": result.get("startedAtUtc"),
        "finishedAtUtc": result.get("finishedAtUtc"),
        "exitCode": result.get("exitCode"),
        "success": bool(result.get("success")),
    }
    if output_path is not None:
        summary["outputPath"] = repo_relative(repo_root, output_path) if repo_root is not None else output_path.as_posix()
    stderr = (result.get("stderr") or "").strip()
    if stderr:
        summary["stderrPreview"] = stderr[:2000]
    return summary


def trim_text(value: str, max_characters: int) -> str:
    if max_characters <= 0 or len(value) <= max_characters:
        return value
    omitted = len(value) - max_characters
    return value[:max_characters] + f"\n\n--- output truncated, omitted {omitted} characters ---\n"


def write_command_output(path: Path, result: Dict[str, Any], max_characters: int = 120000) -> None:
    stdout = trim_text(result.get("stdout") or "", max_characters)
    stderr = trim_text(result.get("stderr") or "", max_characters)
    content = stdout
    if stderr:
        content += ("\n" if content and not content.endswith("\n") else "")
        content += "--- STDERR ---\n" + stderr
    if not content:
        content = ""
    write_text(path, content)


def run_persisted_command(
    repo_root: Path,
    command: List[str],
    output_path: Path,
    timeout: Optional[int],
    max_characters: int,
) -> Dict[str, Any]:
    result = run_command(command, timeout=timeout)
    write_command_output(output_path, result, max_characters=max_characters)
    return command_result_summary(result, output_path=output_path, repo_root=repo_root)


def tool_available(command: str) -> bool:
    return shutil.which(command) is not None or Path(command).expanduser().exists()


def kubectl_base(kubectl: str, kubeconfig: Optional[Path]) -> List[str]:
    command = [kubectl]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    return command


def helm_base(helm: str, kubeconfig: Optional[Path]) -> List[str]:
    command = [helm]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    return command


def kubectl_json(kubectl: str, kubeconfig: Optional[Path], args: List[str]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    command = kubectl_base(kubectl, kubeconfig) + args + ["-o", "json"]
    result = run_command(command)
    if not result.get("success"):
        return {}, result
    try:
        return json.loads(result.get("stdout") or "{}"), result
    except Exception as exc:
        result["success"] = False
        result["exitCode"] = 1
        result["stderr"] = f"Unable to parse kubectl JSON output: {exc}"
        return {}, result


def build_affinity(preferred: Dict[str, Any]) -> Dict[str, Any]:
    if not preferred:
        return {}
    return {
        "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [
                {
                    "weight": int(preferred.get("weight", 100)),
                    "preference": {
                        "matchExpressions": [
                            {
                                "key": preferred.get("key", "nodepool"),
                                "operator": preferred.get("operator", "In"),
                                "values": preferred.get("values", ["management"]),
                            }
                        ]
                    },
                }
            ]
        }
    }


def scheduler_environment_variables(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    scheduler = profile.get("scheduler") or {}
    raw = scheduler.get("environmentVariables") or scheduler.get("env") or []
    if isinstance(raw, dict):
        raw = [{"name": key, "value": value} for key, value in raw.items()]
    result: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        result.append({"name": name, "value": str(item.get("value") or "")})
    return result


def environment_map(items: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in items:
        if isinstance(item, dict) and item.get("name"):
            out[str(item.get("name"))] = str(item.get("value") or "")
    return out


def scheduler_container_from_deployment(deployment: Dict[str, Any], expected_container_name: str) -> Dict[str, Any]:
    containers = nested_get(deployment, "spec", "template", "spec", "containers", default=[]) or []
    if not isinstance(containers, list):
        return {}
    for container in containers:
        if isinstance(container, dict) and container.get("name") == expected_container_name:
            return container
    for container in containers:
        if isinstance(container, dict) and "scheduler" in str(container.get("name") or ""):
            return container
    return containers[0] if containers and isinstance(containers[0], dict) else {}


def apply_scheduler_environment_variables(
    kubectl: str,
    kubeconfig: Optional[Path],
    namespace: str,
    deployment_name: str,
    environment: List[Dict[str, str]],
) -> Dict[str, Any]:
    if not environment:
        return {
            "command": [],
            "startedAtUtc": utc_now(),
            "finishedAtUtc": utc_now(),
            "exitCode": 0,
            "stdout": "",
            "stderr": "",
            "success": True,
            "skipped": True,
        }
    assignments = [f"{item['name']}={item.get('value', '')}" for item in environment]
    command = kubectl_base(kubectl, kubeconfig) + ["set", "env", f"deployment/{deployment_name}", "-n", namespace] + assignments
    return run_command(command)


def toleration_key(toleration: Dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(toleration.get("key") or ""),
        str(toleration.get("operator") or ""),
        str(toleration.get("value") or ""),
        str(toleration.get("effect") or ""),
    )


def has_expected_tolerations(deployment: Dict[str, Any], expected: List[Dict[str, Any]]) -> bool:
    if not expected:
        return True
    pod_spec = (((deployment.get("spec") or {}).get("template") or {}).get("spec") or {})
    actual = pod_spec.get("tolerations") or []
    actual_keys = {toleration_key(item) for item in actual if isinstance(item, dict)}
    return all(toleration_key(item) in actual_keys for item in expected if isinstance(item, dict))


def add_finding(findings: List[Dict[str, Any]], severity: str, code: str, message: str, **details: Any) -> None:
    item: Dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if details:
        item["details"] = details
    findings.append(item)


def validate_expected_value(findings: List[Dict[str, Any]], source: Dict[str, Any], path: str, expected: Any, code_prefix: str) -> None:
    actual = dotted_get(source, path)
    if actual != expected:
        add_finding(
            findings,
            "error",
            f"{code_prefix}_MISMATCH",
            f"Expected {path} to be {expected!r}, found {actual!r}.",
            path=path,
            expected=expected,
            actual=actual,
        )


def validate_list_contains(findings: List[Dict[str, Any]], source: Dict[str, Any], path: str, expected_items: List[str], code_prefix: str) -> None:
    actual = dotted_get(source, path, default=[])
    if not isinstance(actual, list):
        add_finding(
            findings,
            "error",
            f"{code_prefix}_NOT_A_LIST",
            f"Expected {path} to be a list, found {type(actual).__name__}.",
            path=path,
            actual=actual,
        )
        return
    missing = [item for item in expected_items if item not in actual]
    if missing:
        add_finding(
            findings,
            "error",
            f"{code_prefix}_MISSING_ITEMS",
            f"Expected {path} to contain {missing}.",
            path=path,
            expectedItems=expected_items,
            actual=actual,
            missing=missing,
        )


def _replace_in_file(path: Path, replacements: List[tuple[str, str]]) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    changes: List[Dict[str, Any]] = []
    for old, new in replacements:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
        changes.append({"old": old, "new": new, "replacementCount": count})
    path.write_text(text, encoding="utf-8")
    return changes


def prepare_scheduler_chart(
    repo_root: Path,
    profile: Dict[str, Any],
    source_chart_path: Path,
    artifact_root: Path,
    run_id: str,
) -> Dict[str, Any]:
    policy = profile.get("chartPatchPolicy") or {}
    enabled = bool(policy.get("enabled", False))
    result: Dict[str, Any] = {
        "enabled": enabled,
        "sourceChartPath": repo_relative(repo_root, source_chart_path),
        "effectiveChartPath": repo_relative(repo_root, source_chart_path),
        "patches": [],
        "status": "skipped" if not enabled else "pending",
    }
    if not enabled:
        return result
    if not source_chart_path.is_dir():
        result["status"] = "failed"
        result["error"] = f"Scheduler chart directory not found: {source_chart_path}"
        return result

    target_root = artifact_root / "rendered-chart" / run_id / source_chart_path.name
    if target_root.exists():
        shutil.rmtree(target_root)
    shutil.copytree(source_chart_path, target_root)

    if bool(policy.get("preservePluginNameCase", True)):
        target = target_root / "templates" / "configmap.yaml"
        changes = _replace_in_file(target, [("{{ title . }}", "{{ . }}")])
        result["patches"].append({
            "patchId": "preserve_plugin_name_case",
            "target": repo_relative(repo_root, target),
            "changes": changes,
        })

    if bool(policy.get("enableSchedulerExtraEnv", True)):
        target = target_root / "templates" / "deployment.yaml"
        marker = "        imagePullPolicy: IfNotPresent\n        livenessProbe:"
        replacement = (
            "        imagePullPolicy: IfNotPresent\n"
            "        {{- with .Values.scheduler.extraEnv }}\n"
            "        env:\n"
            "{{ toYaml . | nindent 10 }}\n"
            "        {{- end }}\n"
            "        livenessProbe:"
        )
        if ".Values.scheduler.extraEnv" not in target.read_text(encoding="utf-8", errors="replace"):
            changes = _replace_in_file(target, [(marker, replacement)])
        else:
            changes = [{"old": marker, "new": replacement, "replacementCount": 0, "alreadyPresent": True}]
        result["patches"].append({
            "patchId": "scheduler_extra_env",
            "target": repo_relative(repo_root, target),
            "changes": changes,
        })

    result["effectiveChartPath"] = repo_relative(repo_root, target_root)
    result["status"] = "patched"
    return result


def validate_scheduler_plugins_chart(
    repo_root: Path,
    profile: Dict[str, Any],
    scheduler_plugins_root: Path,
    chart_path: Path,
    rendered_values: Dict[str, Any],
) -> Dict[str, Any]:
    policy = profile.get("chartValidation") or {}
    enabled = bool(policy.get("enabled", True))
    findings: List[Dict[str, Any]] = []
    chart_metadata: Dict[str, Any] = {}
    values_metadata: Dict[str, Any] = {}
    file_digests: List[Dict[str, Any]] = []
    source_evidence: List[Dict[str, Any]] = []

    if not enabled:
        return {
            "enabled": False,
            "status": "skipped",
            "findings": findings,
            "schedulerPluginsRoot": repo_relative(repo_root, scheduler_plugins_root),
            "chartPath": repo_relative(repo_root, chart_path),
        }

    if not scheduler_plugins_root.is_dir():
        add_finding(findings, "error", "SCHEDULER_PLUGINS_ROOT_NOT_FOUND", f"Scheduler plugins root was not found: {scheduler_plugins_root}")
    if not chart_path.is_dir():
        add_finding(findings, "error", "SCHEDULER_PLUGINS_CHART_NOT_FOUND", f"Scheduler plugins chart directory was not found: {chart_path}")

    required_files = policy.get("requiredChartFiles") or [
        "Chart.yaml",
        "values.yaml",
        "templates/configmap.yaml",
        "templates/deployment.yaml",
        "templates/rbac.yaml",
        "templates/serviceaccount.yaml",
    ]
    for relative in required_files:
        candidate = chart_path / relative
        if not candidate.is_file():
            add_finding(findings, "error", "REQUIRED_CHART_FILE_MISSING", f"Required scheduler chart file is missing: {relative}", file=relative)
        else:
            try:
                file_digests.append({"path": relative, "sha256": sha256_file(candidate)})
            except Exception as exc:
                add_finding(findings, "warning", "CHART_FILE_DIGEST_FAILED", f"Unable to compute digest for scheduler chart file {relative}: {exc}", file=relative)

    chart_file = chart_path / "Chart.yaml"
    if chart_file.is_file():
        try:
            chart_metadata = load_yaml(chart_file)
        except Exception as exc:
            add_finding(findings, "error", "CHART_METADATA_READ_FAILED", f"Unable to read scheduler chart metadata: {exc}")
    values_file = chart_path / "values.yaml"
    if values_file.is_file():
        try:
            values_metadata = load_yaml(values_file)
        except Exception as exc:
            add_finding(findings, "error", "CHART_VALUES_READ_FAILED", f"Unable to read scheduler chart values.yaml: {exc}")

    expected_chart = policy.get("expectedChart") or {}
    for key in ["name", "version", "appVersion", "type"]:
        if key in expected_chart:
            validate_expected_value(findings, chart_metadata, key, expected_chart[key], "CHART_METADATA")

    expected_defaults = policy.get("expectedChartDefaults") or {}
    for path, expected in expected_defaults.items():
        validate_expected_value(findings, values_metadata, path, expected, "CHART_DEFAULT")

    expected_rendered = policy.get("expectedRenderedValues") or {}
    for path, expected in (expected_rendered.get("exact") or {}).items():
        validate_expected_value(findings, rendered_values, path, expected, "RENDERED_VALUES")
    for path, expected_items in (expected_rendered.get("contains") or {}).items():
        validate_list_contains(findings, rendered_values, path, list(expected_items), "RENDERED_VALUES")

    markers = policy.get("requiredTemplateMarkers") or []
    for marker in markers:
        relative = marker.get("file")
        if not relative:
            continue
        candidate = chart_path / str(relative)
        if not candidate.is_file():
            add_finding(findings, "error", "TEMPLATE_MARKER_FILE_MISSING", f"Template marker file is missing: {relative}", file=relative)
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        for expected_text in marker.get("contains", []) or []:
            if str(expected_text) not in text:
                add_finding(findings, "error", "TEMPLATE_MARKER_NOT_FOUND", f"Expected marker {expected_text!r} was not found in {relative}.", file=relative, expectedText=expected_text)

    source_checks = policy.get("requiredSchedulerPluginSources") or []
    for check in source_checks:
        relative = check.get("path")
        if not relative:
            continue
        candidate = scheduler_plugins_root / str(relative)
        evidence: Dict[str, Any] = {"path": relative, "exists": candidate.is_file()}
        if not candidate.is_file():
            add_finding(findings, "error", "REQUIRED_PLUGIN_SOURCE_MISSING", f"Required scheduler plugin source file is missing: {relative}", file=relative)
        else:
            evidence["sha256"] = sha256_file(candidate)
            text = candidate.read_text(encoding="utf-8", errors="replace")
            for expected_text in check.get("contains", []) or []:
                if str(expected_text) not in text:
                    add_finding(findings, "error", "PLUGIN_SOURCE_MARKER_NOT_FOUND", f"Expected marker {expected_text!r} was not found in scheduler plugin source {relative}.", file=relative, expectedText=expected_text)
        source_evidence.append(evidence)

    status = "validated" if not any(item.get("severity") == "error" for item in findings) else "failed"
    return {
        "enabled": True,
        "status": status,
        "schedulerPluginsRoot": repo_relative(repo_root, scheduler_plugins_root),
        "chartPath": repo_relative(repo_root, chart_path),
        "chartMetadata": chart_metadata,
        "valuesMetadata": values_metadata,
        "fileDigests": file_digests,
        "requiredPluginSources": source_evidence,
        "findings": findings,
    }


def render_helm_values(profile: Dict[str, Any]) -> Dict[str, Any]:
    scheduler = profile.get("scheduler") or {}
    controller = profile.get("controller") or {}
    plugins = profile.get("plugins") or {}
    placement = profile.get("placement") or {}

    values: Dict[str, Any] = {
        "scheduler": {
            "name": scheduler.get("name", "scheduler-plugins-scheduler"),
            "image": scheduler.get("image", "ghcr.io/unict-cclab/kube-scheduler:sophos-v0.2.4"),
            "replicaCount": int(scheduler.get("replicaCount", 1)),
            "leaderElect": bool(scheduler.get("leaderElect", False)),
        },
        "controller": {
            "name": controller.get("name", "scheduler-plugins-controller"),
            "image": controller.get("image", "registry.k8s.io/scheduler-plugins/controller:v0.29.7"),
            "replicaCount": int(controller.get("replicaCount", 1)),
        },
        "plugins": {
            "enabled": plugins.get("enabled", ["LoadAwareResourcesBalancedAllocation"]),
            "disabled": plugins.get("disabled", []),
        },
    }
    scheduler_env = scheduler_environment_variables(profile)
    if scheduler_env:
        values["scheduler"]["extraEnv"] = scheduler_env

    plugin_config = plugins.get("pluginConfig", [])
    if plugin_config is None:
        plugin_config = []
    values["pluginConfig"] = plugin_config

    scheduler_affinity = build_affinity(placement.get("schedulerPreferredNodeAffinity") or {})
    if scheduler_affinity:
        values["scheduler"]["affinity"] = scheduler_affinity
    controller_affinity = build_affinity(placement.get("controllerPreferredNodeAffinity") or {})
    if controller_affinity:
        values["controller"]["affinity"] = controller_affinity
    values["scheduler"]["tolerations"] = placement.get("schedulerTolerations", [])
    values["controller"]["tolerations"] = placement.get("controllerTolerations", [])
    return values


def resolve_scheduler_plugins_root(repo_root: Path, profile: Dict[str, Any], explicit_root: Optional[str]) -> Path:
    value = explicit_root or nested_get(profile, "tooling", "schedulerPluginsRootPath", default="../scheduler-plugins")
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def resolve_chart_path(repo_root: Path, profile: Dict[str, Any], scheduler_plugins_root: Path, explicit_chart: Optional[str]) -> Path:
    raw = explicit_chart or nested_get(profile, "tooling", "chartPath", default=None)
    if raw:
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = repo_root / path
        return path.resolve()
    relative = nested_get(profile, "tooling", "chartPathFromSchedulerPluginsRoot", default="manifests/install/charts/as-a-second-scheduler")
    return (scheduler_plugins_root / relative).resolve()


def render_test_deployment(profile: Dict[str, Any]) -> Dict[str, Any]:
    validation = profile.get("validation") or {}
    namespace = validation.get("namespace", "scheduler-validation")
    name = validation.get("testDeploymentName", "scheduler-validation-pod")
    scheduler_name = validation.get("testSchedulerName") or nested_get(profile, "scheduler", "name", default="scheduler-plugins-scheduler")
    labels = validation.get("testLabels") or {"group": "scheduler-validation", "app": name}
    annotations = validation.get("testDeploymentAnnotations") or {"cpu-usage": "0", "memory-usage": "0"}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": labels,
            "annotations": annotations,
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {
                    "labels": labels,
                },
                "spec": {
                    "schedulerName": scheduler_name,
                    "containers": [
                        {
                            "name": "pause",
                            "image": validation.get("testImage", "registry.k8s.io/pause:3.9"),
                            "resources": {
                                "requests": {"cpu": "5m", "memory": "16Mi"},
                                "limits": {"cpu": "50m", "memory": "64Mi"},
                            },
                        }
                    ],
                },
            },
        },
    }


def apply_manifest(kubectl: str, kubeconfig: Optional[Path], manifest: Dict[str, Any]) -> Dict[str, Any]:
    command = kubectl_base(kubectl, kubeconfig) + ["apply", "-f", "-"]
    return run_command(command, stdin=json.dumps(manifest))


def delete_manifest(kubectl: str, kubeconfig: Optional[Path], manifest: Dict[str, Any], ignore_not_found: bool = True) -> Dict[str, Any]:
    command = kubectl_base(kubectl, kubeconfig) + ["delete", "-f", "-"]
    if ignore_not_found:
        command.append("--ignore-not-found=true")
    return run_command(command, stdin=json.dumps(manifest))


def ensure_namespace(kubectl: str, kubeconfig: Optional[Path], namespace: str) -> Dict[str, Any]:
    manifest = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}
    return apply_manifest(kubectl, kubeconfig, manifest)


def deployment_available(deployment: Dict[str, Any], expected_replicas: int) -> bool:
    status = deployment.get("status") or {}
    return int(status.get("availableReplicas") or 0) >= expected_replicas


def get_scheduler_pod_items(kubectl: str, kubeconfig: Optional[Path], namespace: str, scheduler_deployment_name: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    selector = "component=scheduler"
    pods, result = kubectl_json(kubectl, kubeconfig, ["get", "pods", "-n", namespace, "-l", selector])
    items = pods.get("items") or []
    if not items:
        pods, result = kubectl_json(kubectl, kubeconfig, ["get", "pods", "-n", namespace])
        items = [item for item in pods.get("items", []) if item.get("metadata", {}).get("name", "").startswith(scheduler_deployment_name)]
    return items, result


def validate_scheduler_installation(repo_root: Path, profile: Dict[str, Any], kubeconfig: Optional[Path], artifact_root: Path, run_id: str, cleanup_test_workload: bool, skip_test_workload: bool) -> Dict[str, Any]:
    kubectl = nested_get(profile, "tooling", "kubectl", default="kubectl")
    helm_release = profile.get("helmRelease") or {}
    scheduler = profile.get("scheduler") or {}
    controller = profile.get("controller") or {}
    plugins = profile.get("plugins") or {}
    validation = profile.get("validation") or {}

    namespace = helm_release.get("namespace", "scheduler-plugins")
    scheduler_name = scheduler.get("name", "scheduler-plugins-scheduler")
    scheduler_deployment_name = scheduler.get("expectedDeploymentName", scheduler_name)
    controller_deployment_name = controller.get("expectedDeploymentName", controller.get("name", "scheduler-plugins-controller"))

    commands: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []
    snapshots: Dict[str, Any] = {}

    scheduler_deploy, scheduler_deploy_result = kubectl_json(kubectl, kubeconfig, ["get", "deployment", scheduler_deployment_name, "-n", namespace])
    commands.append({"id": "get_scheduler_deployment", **scheduler_deploy_result})
    snapshots["schedulerDeployment"] = scheduler_deploy
    if not scheduler_deploy_result.get("success"):
        findings.append({"severity": "error", "code": "SCHEDULER_DEPLOYMENT_NOT_FOUND", "message": f"Scheduler deployment {namespace}/{scheduler_deployment_name} was not found."})
    elif validation.get("requireSchedulerDeploymentAvailable", True) and not deployment_available(scheduler_deploy, int(scheduler.get("replicaCount", 1))):
        findings.append({"severity": "error", "code": "SCHEDULER_DEPLOYMENT_NOT_AVAILABLE", "message": f"Scheduler deployment {namespace}/{scheduler_deployment_name} is not available."})
    elif validation.get("requireConfiguredTolerations", False) and not has_expected_tolerations(scheduler_deploy, (profile.get("placement") or {}).get("schedulerTolerations") or []):
        findings.append({"severity": "error", "code": "SCHEDULER_TOLERATIONS_NOT_APPLIED", "message": f"Scheduler deployment {namespace}/{scheduler_deployment_name} does not expose the configured management-node tolerations."})

    if scheduler_deploy_result.get("success") and validation.get("requireSchedulerEnvironmentVariables", False):
        expected_env = validation.get("requiredSchedulerEnvironmentVariables") or environment_map(scheduler_environment_variables(profile))
        expected_container = scheduler.get("expectedContainerName", scheduler_deployment_name)
        container = scheduler_container_from_deployment(scheduler_deploy, expected_container)
        actual_env = environment_map(container.get("env") or [])
        for env_name, expected_value in expected_env.items():
            actual_value = actual_env.get(env_name)
            if actual_value != str(expected_value):
                findings.append({
                    "severity": "error",
                    "code": "SCHEDULER_ENVIRONMENT_VARIABLE_MISSING_OR_INVALID",
                    "message": f"Scheduler deployment {namespace}/{scheduler_deployment_name} must expose {env_name}={expected_value}.",
                    "details": {"name": env_name, "expected": str(expected_value), "actual": actual_value},
                })

    controller_deploy, controller_deploy_result = kubectl_json(kubectl, kubeconfig, ["get", "deployment", controller_deployment_name, "-n", namespace])
    commands.append({"id": "get_controller_deployment", **controller_deploy_result})
    snapshots["controllerDeployment"] = controller_deploy
    if validation.get("requireControllerDeploymentAvailable", True):
        if not controller_deploy_result.get("success"):
            findings.append({"severity": "error", "code": "CONTROLLER_DEPLOYMENT_NOT_FOUND", "message": f"Scheduler controller deployment {namespace}/{controller_deployment_name} was not found."})
        elif not deployment_available(controller_deploy, int(controller.get("replicaCount", 1))):
            findings.append({"severity": "error", "code": "CONTROLLER_DEPLOYMENT_NOT_AVAILABLE", "message": f"Scheduler controller deployment {namespace}/{controller_deployment_name} is not available."})
        elif validation.get("requireConfiguredTolerations", False) and not has_expected_tolerations(controller_deploy, (profile.get("placement") or {}).get("controllerTolerations") or []):
            findings.append({"severity": "error", "code": "CONTROLLER_TOLERATIONS_NOT_APPLIED", "message": f"Scheduler controller deployment {namespace}/{controller_deployment_name} does not expose the configured management-node tolerations."})

    configmap, configmap_result = kubectl_json(kubectl, kubeconfig, ["get", "configmap", "scheduler-config", "-n", namespace])
    commands.append({"id": "get_scheduler_configmap", **configmap_result})
    snapshots["schedulerConfigMap"] = configmap
    config_text = nested_get(configmap, "data", "scheduler-config.yaml", default="") or ""
    required_plugins = plugins.get("requiredEnabledPlugins") or plugins.get("enabled") or []
    if validation.get("requireSchedulerConfigPlugin", True):
        if scheduler_name not in config_text:
            findings.append({"severity": "error", "code": "SCHEDULER_NAME_NOT_IN_CONFIG", "message": f"Scheduler name {scheduler_name} was not found in scheduler-config ConfigMap."})
        for plugin in required_plugins:
            if plugin not in config_text:
                findings.append({"severity": "error", "code": "REQUIRED_PLUGIN_NOT_IN_CONFIG", "message": f"Required plugin {plugin} was not found in scheduler-config ConfigMap."})

    scheduler_pods, scheduler_pods_result = get_scheduler_pod_items(kubectl, kubeconfig, namespace, scheduler_deployment_name)
    commands.append({"id": "get_scheduler_pods", **scheduler_pods_result})
    snapshots["schedulerPods"] = scheduler_pods

    test_result: Dict[str, Any] = {"skipped": bool(skip_test_workload)}
    if not skip_test_workload:
        test_ns = validation.get("namespace", "scheduler-validation")
        test_deployment = validation.get("testDeploymentName", "scheduler-validation-pod")
        label_selector = ",".join(f"{key}={value}" for key, value in (validation.get("testLabels") or {"app": test_deployment}).items())
        test_manifest = render_test_deployment(profile)
        namespace_result = ensure_namespace(kubectl, kubeconfig, test_ns)
        apply_result = apply_manifest(kubectl, kubeconfig, test_manifest)
        commands.append({"id": "ensure_validation_namespace", **namespace_result})
        commands.append({"id": "apply_scheduler_validation_deployment", **apply_result})
        if not namespace_result.get("success") or not apply_result.get("success"):
            findings.append({"severity": "error", "code": "TEST_WORKLOAD_APPLY_FAILED", "message": "Unable to create scheduler validation workload."})
        else:
            timeout = int(validation.get("podScheduledTimeoutSeconds", 120))
            wait_deadline = time.time() + timeout
            observed_pod: Optional[Dict[str, Any]] = None
            pod_scheduled = False
            polling_commands: List[Dict[str, Any]] = []
            while time.time() < wait_deadline:
                pods, pods_result = kubectl_json(kubectl, kubeconfig, ["get", "pods", "-n", test_ns, "-l", label_selector])
                polling_commands.append(pods_result)
                items = pods.get("items") or []
                if items:
                    observed_pod = items[0]
                    for condition in observed_pod.get("status", {}).get("conditions", []) or []:
                        if condition.get("type") == "PodScheduled" and condition.get("status") == "True":
                            pod_scheduled = True
                            break
                    if pod_scheduled or observed_pod.get("spec", {}).get("nodeName"):
                        pod_scheduled = True
                        break
                time.sleep(5)
            commands.append({"id": "poll_scheduler_validation_pod", "polls": polling_commands, "success": pod_scheduled, "exitCode": 0 if pod_scheduled else 1})
            test_result = {
                "skipped": False,
                "namespace": test_ns,
                "deploymentName": test_deployment,
                "labelSelector": label_selector,
                "podScheduled": pod_scheduled,
                "observedPod": observed_pod,
                "schedulerName": nested_get(observed_pod or {}, "spec", "schedulerName", default=None),
                "nodeName": nested_get(observed_pod or {}, "spec", "nodeName", default=None),
            }
            snapshots["validationWorkload"] = test_result
            if validation.get("requireTestPodScheduled", True):
                if not pod_scheduled:
                    findings.append({"severity": "error", "code": "TEST_POD_NOT_SCHEDULED", "message": f"Validation pod was not scheduled by {scheduler_name} within {timeout} seconds."})
                if test_result.get("schedulerName") != scheduler_name:
                    findings.append({"severity": "error", "code": "TEST_POD_SCHEDULER_NAME_MISMATCH", "message": f"Validation pod did not report schedulerName {scheduler_name}."})

            events, events_result = kubectl_json(kubectl, kubeconfig, ["get", "events", "-n", test_ns, "--sort-by=.lastTimestamp"])
            commands.append({"id": "get_validation_namespace_events", **events_result})
            snapshots["validationNamespaceEvents"] = events

        if cleanup_test_workload or validation.get("deleteTestWorkloadAfterValidation", True):
            delete_result = delete_manifest(kubectl, kubeconfig, test_manifest, ignore_not_found=True)
            commands.append({"id": "delete_scheduler_validation_deployment", **delete_result})
            namespace_delete_cmd = kubectl_base(kubectl, kubeconfig) + ["delete", "namespace", test_ns, "--ignore-not-found=true"]
            namespace_delete_result = run_command(namespace_delete_cmd)
            commands.append({"id": "delete_scheduler_validation_namespace", **namespace_delete_result})

    status = "validated" if not any(f.get("severity") == "error" for f in findings) else "failed"
    snapshot = {
        "schemaVersion": "custom-scheduler-validation-snapshot/v1",
        "generatedAtUtc": utc_now(),
        "status": status,
        "schedulerName": scheduler_name,
        "namespace": namespace,
        "requiredPlugins": required_plugins,
        "findings": findings,
        "testWorkload": test_result,
        "snapshots": snapshots,
        "commands": commands,
    }
    snapshot_path = artifact_root / "snapshots" / f"{run_id}.custom-scheduler-validation-snapshot.json"
    write_json(snapshot_path, snapshot)
    return {"status": status, "snapshotPath": snapshot_path, "snapshot": snapshot}


def capture_scheduler_state(repo_root: Path, profile: Dict[str, Any], kubeconfig: Optional[Path], artifact_root: Path, run_id: str) -> Dict[str, Any]:
    kubectl = nested_get(profile, "tooling", "kubectl", default="kubectl")
    namespace = nested_get(profile, "helmRelease", "namespace", default="scheduler-plugins")
    scheduler_name = nested_get(profile, "scheduler", "expectedDeploymentName", default=nested_get(profile, "scheduler", "name", default="scheduler-plugins-scheduler"))
    controller_name = nested_get(profile, "controller", "expectedDeploymentName", default=nested_get(profile, "controller", "name", default="scheduler-plugins-controller"))

    commands = []
    snapshots: Dict[str, Any] = {}

    capture_targets = [
        ("namespace", ["get", "namespace", namespace]),
        ("pods", ["get", "pods", "-n", namespace]),
        ("deployments", ["get", "deployments", "-n", namespace]),
        ("configmaps", ["get", "configmaps", "-n", namespace]),
        ("events", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
    ]
    for target_id, args in capture_targets:
        payload, result = kubectl_json(kubectl, kubeconfig, args)
        commands.append({"id": f"capture_{target_id}", **result})
        snapshots[target_id] = payload
        write_json(artifact_root / "snapshots" / f"{run_id}.{target_id}.json", payload)

    log_targets = [
        ("scheduler", scheduler_name),
        ("controller", controller_name),
    ]
    log_results: Dict[str, Any] = {}
    for log_id, deployment_name in log_targets:
        command = kubectl_base(kubectl, kubeconfig) + ["logs", "-n", namespace, f"deployment/{deployment_name}", "--all-containers=true", "--tail=500"]
        result = run_command(command)
        commands.append({"id": f"logs_{log_id}", **result})
        log_results[log_id] = result
        log_path = artifact_root / "logs" / f"{run_id}.{log_id}.log"
        write_text(log_path, (result.get("stdout") or "") + (("\n--- STDERR ---\n" + result.get("stderr", "")) if result.get("stderr") else ""))

    status = "captured" if any(item.get("success") for item in commands) else "failed"
    snapshot = {
        "schemaVersion": "custom-scheduler-capture/v1",
        "generatedAtUtc": utc_now(),
        "status": status,
        "namespace": namespace,
        "commands": commands,
        "snapshots": snapshots,
        "logs": {key: {"success": value.get("success"), "exitCode": value.get("exitCode")} for key, value in log_results.items()},
    }
    snapshot_path = artifact_root / "snapshots" / f"{run_id}.custom-scheduler-capture.json"
    write_json(snapshot_path, snapshot)
    return {"status": status, "snapshotPath": snapshot_path, "snapshot": snapshot}


def collect_install_failure_diagnostics(
    repo_root: Path,
    profile: Dict[str, Any],
    kubeconfig: Optional[Path],
    artifact_root: Path,
    run_id: str,
    helm_result: Dict[str, Any],
) -> Dict[str, Any]:
    policy = profile.get("installFailureDiagnostics") or {}
    enabled = bool(policy.get("enabled", True))
    namespace = nested_get(profile, "helmRelease", "namespace", default="scheduler-plugins")
    scheduler_name = nested_get(profile, "scheduler", "expectedDeploymentName", default=nested_get(profile, "scheduler", "name", default="scheduler-plugins-scheduler"))
    controller_name = nested_get(profile, "controller", "expectedDeploymentName", default=nested_get(profile, "controller", "name", default="scheduler-plugins-controller"))
    kubectl = nested_get(profile, "tooling", "kubectl", default="kubectl")
    command_timeout = int(policy.get("commandTimeoutSeconds", 60))
    log_tail_lines = int(policy.get("logTailLines", 300))
    max_output_characters = int(policy.get("maxOutputCharacters", 120000))
    include_previous_logs = bool(policy.get("includePreviousContainerLogs", True))

    diagnostics_root = artifact_root / "diagnostics" / run_id
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    text_root = diagnostics_root / "text"
    json_root = diagnostics_root / "json"
    logs_root = diagnostics_root / "logs"
    text_root.mkdir(parents=True, exist_ok=True)
    json_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    diagnostic_commands: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []
    snapshots: Dict[str, Any] = {}

    if not enabled:
        return {
            "enabled": False,
            "status": "skipped",
            "reason": "installFailureDiagnostics.enabled=false",
        }

    if not tool_available(kubectl):
        finding = {
            "severity": "warning",
            "code": "KUBECTL_NOT_AVAILABLE_FOR_INSTALL_DIAGNOSTICS",
            "message": f"kubectl is not available: {kubectl}",
        }
        findings.append(finding)
        diagnostic_manifest = {
            "schemaVersion": "custom-scheduler-install-failure-diagnostics/v1",
            "generatedAtUtc": utc_now(),
            "status": "failed",
            "namespace": namespace,
            "schedulerDeploymentName": scheduler_name,
            "controllerDeploymentName": controller_name,
            "helmResult": command_result_summary(helm_result, repo_root=repo_root),
            "findings": findings,
            "commands": diagnostic_commands,
            "snapshots": snapshots,
        }
        diagnostic_manifest_path = diagnostics_root / f"{run_id}.install-failure-diagnostics.json"
        write_json(diagnostic_manifest_path, diagnostic_manifest)
        return {
            "enabled": True,
            "status": "failed",
            "diagnosticManifestPath": diagnostic_manifest_path,
            "findings": findings,
            "commands": diagnostic_commands,
        }

    json_targets = [
        ("namespace", ["get", "namespace", namespace]),
        ("deployments", ["get", "deployments", "-n", namespace]),
        ("pods", ["get", "pods", "-n", namespace]),
        ("replicasets", ["get", "replicasets", "-n", namespace]),
        ("events", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
        ("scheduler_deployment", ["get", "deployment", scheduler_name, "-n", namespace]),
        ("controller_deployment", ["get", "deployment", controller_name, "-n", namespace]),
    ]
    for target_id, args in json_targets:
        command = kubectl_base(kubectl, kubeconfig) + args + ["-o", "json"]
        output_path = json_root / f"{target_id}.json"
        result = run_command(command, timeout=command_timeout)
        diagnostic_commands.append(command_result_summary(result, output_path=output_path, repo_root=repo_root))
        payload: Any
        if result.get("success"):
            try:
                payload = json.loads(result.get("stdout") or "{}")
            except Exception as exc:
                payload = {
                    "parseError": str(exc),
                    "stdout": trim_text(result.get("stdout") or "", max_output_characters),
                    "stderr": trim_text(result.get("stderr") or "", max_output_characters),
                }
                findings.append({
                    "severity": "warning",
                    "code": "INSTALL_DIAGNOSTIC_JSON_PARSE_FAILED",
                    "message": f"Unable to parse JSON diagnostic output for {target_id}: {exc}",
                    "details": {"target": target_id},
                })
        else:
            payload = {
                "commandFailed": True,
                "exitCode": result.get("exitCode"),
                "stdout": trim_text(result.get("stdout") or "", max_output_characters),
                "stderr": trim_text(result.get("stderr") or "", max_output_characters),
            }
        snapshots[target_id] = payload
        write_json(output_path, payload)

    text_targets = [
        ("get_all_wide", ["get", "all", "-n", namespace, "-o", "wide"]),
        ("describe_scheduler_deployment", ["describe", "deployment", scheduler_name, "-n", namespace]),
        ("describe_controller_deployment", ["describe", "deployment", controller_name, "-n", namespace]),
        ("describe_pods", ["describe", "pods", "-n", namespace]),
        ("events_wide", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp", "-o", "wide"]),
    ]
    for target_id, args in text_targets:
        command = kubectl_base(kubectl, kubeconfig) + args
        output_path = text_root / f"{target_id}.txt"
        diagnostic_commands.append(run_persisted_command(repo_root, command, output_path, command_timeout, max_output_characters))

    log_targets = [
        ("scheduler_deployment", ["logs", "-n", namespace, f"deployment/{scheduler_name}", "--all-containers=true", f"--tail={log_tail_lines}"]),
        ("controller_deployment", ["logs", "-n", namespace, f"deployment/{controller_name}", "--all-containers=true", f"--tail={log_tail_lines}"]),
        ("scheduler_label", ["logs", "-n", namespace, "-l", "component=scheduler", "--all-containers=true", f"--tail={log_tail_lines}"]),
        ("controller_label", ["logs", "-n", namespace, "-l", "app=scheduler-plugins-controller", "--all-containers=true", f"--tail={log_tail_lines}"]),
    ]
    if include_previous_logs:
        log_targets.extend([
            ("scheduler_deployment_previous", ["logs", "-n", namespace, f"deployment/{scheduler_name}", "--all-containers=true", "--previous", f"--tail={log_tail_lines}"]),
            ("controller_deployment_previous", ["logs", "-n", namespace, f"deployment/{controller_name}", "--all-containers=true", "--previous", f"--tail={log_tail_lines}"]),
        ])
    for target_id, args in log_targets:
        command = kubectl_base(kubectl, kubeconfig) + args
        output_path = logs_root / f"{target_id}.log"
        diagnostic_commands.append(run_persisted_command(repo_root, command, output_path, command_timeout, max_output_characters))

    pod_items = nested_get(snapshots, "pods", "items", default=[]) or []
    scheduler_pods = [
        pod for pod in pod_items
        if str(nested_get(pod, "metadata", "name", default="")).startswith(scheduler_name)
    ]
    for pod in scheduler_pods:
        pod_name = str(nested_get(pod, "metadata", "name", default=""))
        if not pod_name:
            continue
        safe_pod_name = pod_name.replace("/", "_")
        for target_id, args in [
            (f"describe_pod_{safe_pod_name}", ["describe", "pod", pod_name, "-n", namespace]),
            (f"logs_pod_{safe_pod_name}", ["logs", "-n", namespace, pod_name, "--all-containers=true", f"--tail={log_tail_lines}"]),
        ]:
            output_root = logs_root if target_id.startswith("logs_") else text_root
            extension = ".log" if target_id.startswith("logs_") else ".txt"
            command = kubectl_base(kubectl, kubeconfig) + args
            output_path = output_root / f"{target_id}{extension}"
            diagnostic_commands.append(run_persisted_command(repo_root, command, output_path, command_timeout, max_output_characters))
        if include_previous_logs:
            command = kubectl_base(kubectl, kubeconfig) + ["logs", "-n", namespace, pod_name, "--all-containers=true", "--previous", f"--tail={log_tail_lines}"]
            output_path = logs_root / f"logs_pod_{safe_pod_name}_previous.log"
            diagnostic_commands.append(run_persisted_command(repo_root, command, output_path, command_timeout, max_output_characters))

    diagnostic_manifest = {
        "schemaVersion": "custom-scheduler-install-failure-diagnostics/v1",
        "generatedAtUtc": utc_now(),
        "status": "collected" if any(item.get("success") for item in diagnostic_commands) else "failed",
        "namespace": namespace,
        "schedulerDeploymentName": scheduler_name,
        "controllerDeploymentName": controller_name,
        "helmResult": command_result_summary(helm_result, repo_root=repo_root),
        "findings": findings,
        "commands": diagnostic_commands,
        "snapshots": snapshots,
        "diagnosticsRoot": repo_relative(repo_root, diagnostics_root),
    }
    diagnostic_manifest_path = diagnostics_root / f"{run_id}.install-failure-diagnostics.json"
    write_json(diagnostic_manifest_path, diagnostic_manifest)
    return {
        "enabled": True,
        "status": diagnostic_manifest.get("status"),
        "diagnosticManifestPath": diagnostic_manifest_path,
        "diagnosticsRoot": diagnostics_root,
        "findings": findings,
        "commands": diagnostic_commands,
    }


def build_summary(manifest: Dict[str, Any]) -> str:
    lines = [
        "custom scheduler integration summary",
        "====================================",
        f"Profile: {manifest.get('schedulerProfileId')}",
        f"Action: {manifest.get('action')}",
        f"Status: {manifest.get('status')}",
        f"Generated at UTC: {manifest.get('generatedAtUtc')}",
        f"Scheduler name: {nested_get(manifest, 'resolved', 'schedulerName', default='')}",
        f"Helm release: {nested_get(manifest, 'resolved', 'helmReleaseName', default='')}",
        f"Helm namespace: {nested_get(manifest, 'resolved', 'helmNamespace', default='')}",
        f"Chart path: {nested_get(manifest, 'resolved', 'chartPath', default='')}",
    ]
    chart_patch = manifest.get("chartPatch") or {}
    if chart_patch:
        lines.extend([
            f"Chart patch status: {chart_patch.get('status')}",
            f"Source chart path: {chart_patch.get('sourceChartPath')}",
        ])
    chart_validation = manifest.get("chartValidation") or {}
    if chart_validation:
        lines.extend([
            "",
            "Chart validation:",
            f"  Status: {chart_validation.get('status')}",
            f"  Chart metadata: {chart_validation.get('chartMetadata')}",
        ])
        chart_findings = chart_validation.get("findings") or []
        lines.append(f"  Findings: {len(chart_findings)}")
        for finding in chart_findings[:10]:
            lines.append(f"  - {finding.get('severity')}: {finding.get('code')} - {finding.get('message')}")

    install_diagnostics = manifest.get("installDiagnostics") or {}
    if install_diagnostics:
        lines.extend([
            "",
            "Install failure diagnostics:",
            f"  Status: {install_diagnostics.get('status')}",
            f"  Manifest: {install_diagnostics.get('diagnosticManifestPath')}",
            f"  Diagnostics root: {install_diagnostics.get('diagnosticsRoot')}",
            f"  Commands: {len(install_diagnostics.get('commands') or [])}",
        ])
        diagnostic_findings = install_diagnostics.get("findings") or []
        lines.append(f"  Findings: {len(diagnostic_findings)}")
        for finding in diagnostic_findings[:10]:
            lines.append(f"  - {finding.get('severity')}: {finding.get('code')} - {finding.get('message')}")

    validation = manifest.get("validation") or {}
    if validation:
        lines.extend([
            "",
            "Validation:",
            f"  Status: {validation.get('status')}",
            f"  Snapshot: {validation.get('snapshotPath')}",
        ])
        findings = nested_get(validation, "snapshot", "findings", default=[]) or []
        lines.append(f"  Findings: {len(findings)}")
        for finding in findings[:10]:
            lines.append(f"  - {finding.get('severity')}: {finding.get('code')} - {finding.get('message')}")
    command_results = manifest.get("commandResults") or []
    if command_results:
        lines.append("")
        lines.append("Command results:")
        for item in command_results:
            lines.append(f"  - {item.get('id')}: {'completed' if item.get('success') else 'failed'} (exitCode={item.get('exitCode')})")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install, validate, capture, and uninstall the scheduler-plugins second scheduler.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--profile-config", default=DEFAULT_PROFILE)
    parser.add_argument("--action", choices=["plan", "install", "apply", "capture", "validate", "uninstall"], default=DEFAULT_ACTION)
    parser.add_argument("--kubeconfig", default=None)
    parser.add_argument("--scheduler-plugins-root", default=None)
    parser.add_argument("--chart-path", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--skip-test-workload", action="store_true")
    parser.add_argument("--keep-test-workload", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    profile_path = repo_path(repo_root, args.profile_config, DEFAULT_PROFILE)
    if profile_path is None or not profile_path.is_file():
        raise FileNotFoundError(f"Custom scheduler profile not found: {profile_path}")
    profile = load_json(profile_path)

    action = "install" if args.action == "apply" else args.action
    run_id = args.run_id or f"{profile.get('schedulerProfileId', 'custom-scheduler')}_{action}_{safe_stamp()}"
    default_scheduler_artifact_root = f"results/experimental-cycles/{profile.get('cycleId', 'C8')}/scheduler/custom-scheduler"
    artifact_root = repo_path(repo_root, args.output_root, nested_get(profile, "artifactPolicy", "root", default=default_scheduler_artifact_root))
    assert artifact_root is not None
    kubeconfig = repo_path(repo_root, args.kubeconfig, profile.get("kubeconfigPath"))
    scheduler_plugins_root = resolve_scheduler_plugins_root(repo_root, profile, args.scheduler_plugins_root)
    chart_path = resolve_chart_path(repo_root, profile, scheduler_plugins_root, args.chart_path)
    chart_patch = prepare_scheduler_chart(repo_root, profile, chart_path, artifact_root, run_id)
    effective_chart_path = repo_path(repo_root, chart_patch.get("effectiveChartPath"), None) or chart_path

    helm = nested_get(profile, "tooling", "helm", default="helm")
    kubectl = nested_get(profile, "tooling", "kubectl", default="kubectl")
    release = profile.get("helmRelease") or {}
    release_name = release.get("name", "scheduler-plugins")
    release_ns = release.get("namespace", "scheduler-plugins")
    scheduler_name = nested_get(profile, "scheduler", "name", default="scheduler-plugins-scheduler")

    values = render_helm_values(profile)
    values_path = artifact_root / "rendered-values" / f"{run_id}.scheduler-plugins-values.yaml"
    write_json(values_path, values)

    command_results: List[Dict[str, Any]] = []
    errors: List[str] = []
    chart_validation: Optional[Dict[str, Any]] = None

    if action in {"plan", "install"} or args.dry_run:
        chart_validation = validate_scheduler_plugins_chart(repo_root, profile, scheduler_plugins_root, effective_chart_path, values)
        chart_validation_status = chart_validation.get("status")
        chart_validation_strict = bool((profile.get("chartValidation") or {}).get("failOnError", True))
        if chart_validation_strict and chart_validation_status == "failed":
            for finding in chart_validation.get("findings") or []:
                if finding.get("severity") == "error":
                    errors.append(f"{finding.get('code')}: {finding.get('message')}")

    if not args.dry_run:
        if action in {"install", "validate", "capture", "uninstall"}:
            if not tool_available(kubectl):
                errors.append(f"kubectl is not available: {kubectl}")
        if action in {"install", "uninstall"}:
            if not tool_available(helm):
                errors.append(f"helm is not available: {helm}")
        if action == "install" and not effective_chart_path.is_dir():
            errors.append(f"Scheduler plugins chart directory not found: {effective_chart_path}")
    elif action == "install" and not effective_chart_path.is_dir():
        errors.append(f"Scheduler plugins chart directory not found: {effective_chart_path}")

    status = nested_get(profile, "decisionPolicy", "plannedStatus", default="planned")
    validation_result: Optional[Dict[str, Any]] = None
    capture_result: Optional[Dict[str, Any]] = None
    install_diagnostics_result: Optional[Dict[str, Any]] = None

    if errors:
        status = nested_get(profile, "decisionPolicy", "failedStatus", default="failed")
    elif args.dry_run or action == "plan":
        status = nested_get(profile, "decisionPolicy", "dryRunStatus", default="dry_run") if args.dry_run else nested_get(profile, "decisionPolicy", "plannedStatus", default="planned")
    elif action == "install":
        helm_cmd = helm_base(helm, kubeconfig) + ["upgrade", "--install", release_name, str(effective_chart_path), "--namespace", release_ns, "--values", str(values_path)]
        if release.get("createNamespace", True):
            helm_cmd.append("--create-namespace")
        if release.get("wait", True):
            helm_cmd.append("--wait")
            helm_cmd.extend(["--timeout", f"{int(release.get('timeoutSeconds', 240))}s"])
        if release.get("atomic", False):
            helm_cmd.append("--atomic")
        helm_result = run_command(helm_cmd, timeout=int(release.get("timeoutSeconds", 240)) + 60)
        command_results.append({"id": "helm_upgrade_install", **helm_result})
        if not helm_result.get("success"):
            status = nested_get(profile, "decisionPolicy", "failedStatus", default="failed")
            install_diagnostics_result = collect_install_failure_diagnostics(
                repo_root,
                profile,
                kubeconfig,
                artifact_root,
                run_id,
                helm_result,
            )
        else:
            scheduler_env = scheduler_environment_variables(profile)
            if scheduler_env:
                env_result = apply_scheduler_environment_variables(kubectl, kubeconfig, release_ns, nested_get(profile, "scheduler", "expectedDeploymentName", default=scheduler_name), scheduler_env)
                command_results.append({"id": "apply_scheduler_environment_variables", **env_result})
                if not env_result.get("success"):
                    status = nested_get(profile, "decisionPolicy", "failedStatus", default="failed")
            capture_result = capture_scheduler_state(repo_root, profile, kubeconfig, artifact_root, run_id)
            if not args.skip_validation and nested_get(profile, "decisionPolicy", "validateAfterInstallByDefault", default=True):
                validation_result = validate_scheduler_installation(
                    repo_root,
                    profile,
                    kubeconfig,
                    artifact_root,
                    run_id,
                    cleanup_test_workload=not args.keep_test_workload,
                    skip_test_workload=args.skip_test_workload,
                )
                status = nested_get(profile, "decisionPolicy", "validatedStatus", default="validated") if validation_result.get("status") == "validated" else nested_get(profile, "decisionPolicy", "failedStatus", default="failed")
            else:
                status = nested_get(profile, "decisionPolicy", "installedStatus", default="installed")
    elif action == "capture":
        capture_result = capture_scheduler_state(repo_root, profile, kubeconfig, artifact_root, run_id)
        status = capture_result.get("status") or nested_get(profile, "decisionPolicy", "capturedStatus", default="captured")
    elif action == "validate":
        validation_result = validate_scheduler_installation(
            repo_root,
            profile,
            kubeconfig,
            artifact_root,
            run_id,
            cleanup_test_workload=not args.keep_test_workload,
            skip_test_workload=args.skip_test_workload,
        )
        status = nested_get(profile, "decisionPolicy", "validatedStatus", default="validated") if validation_result.get("status") == "validated" else nested_get(profile, "decisionPolicy", "failedStatus", default="failed")
    elif action == "uninstall":
        helm_cmd = helm_base(helm, kubeconfig) + ["uninstall", release_name, "--namespace", release_ns]
        helm_result = run_command(helm_cmd, timeout=int(release.get("timeoutSeconds", 240)))
        command_results.append({"id": "helm_uninstall", **helm_result})
        status = nested_get(profile, "decisionPolicy", "uninstalledStatus", default="uninstalled") if helm_result.get("success") else nested_get(profile, "decisionPolicy", "failedStatus", default="failed")

    latest_aliases_enabled = bool(args.write_latest_aliases or nested_get(profile, "artifactPolicy", "writeLatestAliases", default=False))
    latest_manifest = repo_path(repo_root, nested_get(profile, "artifactPolicy", "latestManifestPath", default=None)) if latest_aliases_enabled else None
    latest_summary = repo_path(repo_root, nested_get(profile, "artifactPolicy", "latestSummaryPath", default=None)) if latest_aliases_enabled else None
    latest_validation = repo_path(repo_root, nested_get(profile, "artifactPolicy", "latestValidationSnapshotPath", default=None)) if latest_aliases_enabled else None
    latest_alias_errors = [
        error
        for error in [
            latest_alias_target_error(repo_root, artifact_root, latest_manifest, "custom scheduler latest manifest"),
            latest_alias_target_error(repo_root, artifact_root, latest_summary, "custom scheduler latest summary"),
            latest_alias_target_error(repo_root, artifact_root, latest_validation, "custom scheduler latest validation snapshot"),
        ]
        if error
    ]
    if latest_alias_errors:
        errors.extend(latest_alias_errors)
        status = nested_get(profile, "decisionPolicy", "failedStatus", default="failed")

    manifest = {
        "schemaVersion": "custom-scheduler-integration-manifest/v1",
        "generatedAtUtc": utc_now(),
        "schedulerProfileId": profile.get("schedulerProfileId"),
        "profileConfigPath": repo_relative(repo_root, profile_path),
        "action": action,
        "status": status,
        "dryRun": bool(args.dry_run),
        "errors": errors,
        "resolved": {
            "repoRoot": ".",
            "schedulerPluginsRoot": repo_relative(repo_root, scheduler_plugins_root),
            "chartPath": repo_relative(repo_root, effective_chart_path),
            "sourceChartPath": repo_relative(repo_root, chart_path),
            "kubeconfigPath": repo_relative(repo_root, kubeconfig),
            "helm": helm,
            "kubectl": kubectl,
            "helmReleaseName": release_name,
            "helmNamespace": release_ns,
            "schedulerName": scheduler_name,
            "valuesPath": repo_relative(repo_root, values_path),
        },
        "helmValues": values,
        "chartPatch": chart_patch,
        "chartValidation": chart_validation,
        "commandResults": command_results,
        "installDiagnostics": {
            "enabled": install_diagnostics_result.get("enabled") if install_diagnostics_result else None,
            "status": install_diagnostics_result.get("status") if install_diagnostics_result else None,
            "diagnosticManifestPath": repo_relative(repo_root, install_diagnostics_result.get("diagnosticManifestPath")) if install_diagnostics_result and install_diagnostics_result.get("diagnosticManifestPath") else None,
            "diagnosticsRoot": repo_relative(repo_root, install_diagnostics_result.get("diagnosticsRoot")) if install_diagnostics_result and install_diagnostics_result.get("diagnosticsRoot") else None,
            "findings": install_diagnostics_result.get("findings") if install_diagnostics_result else [],
            "commands": install_diagnostics_result.get("commands") if install_diagnostics_result else [],
        } if install_diagnostics_result else None,
        "capture": {
            "status": capture_result.get("status") if capture_result else None,
            "snapshotPath": repo_relative(repo_root, capture_result.get("snapshotPath")) if capture_result else None,
            "snapshot": capture_result.get("snapshot") if capture_result else None,
        } if capture_result else None,
        "validation": {
            "status": validation_result.get("status") if validation_result else None,
            "snapshotPath": repo_relative(repo_root, validation_result.get("snapshotPath")) if validation_result else None,
            "snapshot": validation_result.get("snapshot") if validation_result else None,
        } if validation_result else None,
    }

    manifest_path = artifact_root / "manifests" / f"{run_id}.custom-scheduler-manifest.json"
    summary_path = artifact_root / "summaries" / f"{run_id}.custom-scheduler-summary.txt"
    write_json(manifest_path, manifest)
    write_text(summary_path, build_summary(manifest))

    if latest_aliases_enabled and not latest_alias_errors:
        if latest_manifest:
            write_json(latest_manifest, manifest)
        if latest_summary:
            write_text(latest_summary, build_summary(manifest))
        if latest_validation and validation_result:
            write_json(latest_validation, validation_result.get("snapshot"))

    print("===============================================")
    print(" custom scheduler integration")
    print("===============================================")
    print(f"Profile : {profile_path}")
    print(f"Action  : {action}")
    print(f"Status  : {status}")
    print(f"Manifest: {manifest_path}")
    print(f"Summary : {summary_path}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"- {error}")

    return 0 if status not in {nested_get(profile, "decisionPolicy", "failedStatus", default="failed"), "failed"} else 2


if __name__ == "__main__":
    sys.exit(main())
