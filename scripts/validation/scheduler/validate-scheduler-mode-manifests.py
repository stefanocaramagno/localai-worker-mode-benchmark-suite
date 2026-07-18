#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except Exception:
    yaml = None

HOSTNAME_SELECTOR_KEYS = {
    "kubernetes.io/hostname",
    "beta.kubernetes.io/hostname",
}

LOCALAI_DEPLOYMENTS = {
    "localai-server",
    "localai-rpc-a",
    "localai-rpc-b",
    "localai-rpc-c",
    "localai-rpc-d",
}

LOCALAI_EXPECTED_ROLES = {
    "localai-server": "master",
    "localai-rpc-a": "worker",
    "localai-rpc-b": "worker",
    "localai-rpc-c": "worker",
    "localai-rpc-d": "worker",
}

KUSTOMIZATION_FILENAMES = {"kustomization.yaml", "kustomization.yml", "Kustomization"}
YAML_SUFFIXES = {".yaml", ".yml"}


@dataclass
class Finding:
    severity: str
    code: str
    path: str
    message: str
    location: str | None = None
    value: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.location is not None:
            payload["location"] = self.location
        if self.value is not None:
            payload["value"] = self.value
        return payload


@dataclass
class ValidationResult:
    repo_root: Path
    scan_roots: list[Path]
    mode: str
    expected_scheduler_name: str
    rendered_manifest_paths: list[Path] = field(default_factory=list)
    source_files_scanned: int = 0
    yaml_documents_scanned: int = 0
    kustomization_files_scanned: int = 0
    rendered_compositions_scanned: int = 0
    localai_deployments_seen: int = 0
    rendered_localai_deployments_seen: int = 0
    render_attempted: bool = False
    render_tool: str | None = None
    render_warnings: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator": "scheduler-mode-manifest-validator",
            "schemaVersion": "scheduler-mode-manifest-validation/v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "repoRoot": repo_relative(self.repo_root, self.repo_root),
            "scanRoots": [repo_relative(path, self.repo_root) for path in self.scan_roots],
            "mode": self.mode,
            "expectedSchedulerName": self.expected_scheduler_name,
            "renderedManifestPaths": [repo_relative(path, self.repo_root) for path in self.rendered_manifest_paths],
            "renderAttempted": self.render_attempted,
            "renderTool": self.render_tool,
            "renderWarnings": self.render_warnings,
            "sourceFilesScanned": self.source_files_scanned,
            "yamlDocumentsScanned": self.yaml_documents_scanned,
            "kustomizationFilesScanned": self.kustomization_files_scanned,
            "renderedCompositionsScanned": self.rendered_compositions_scanned,
            "localaiDeploymentsSeen": self.localai_deployments_seen,
            "renderedLocalaiDeploymentsSeen": self.rendered_localai_deployments_seen,
            "findingCounts": {
                "errors": sum(1 for item in self.findings if item.severity == "error"),
                "warnings": sum(1 for item in self.findings if item.severity == "warning"),
                "total": len(self.findings),
            },
            "passed": self.passed,
            "findings": [item.to_dict() for item in self.findings],
        }


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def resolve_repo_root(candidate: str | None) -> Path:
    if candidate:
        return Path(candidate).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def resolve_path(value: str, repo_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def infer_mode(scan_roots: list[Path], requested_mode: str) -> str:
    if requested_mode != "auto":
        return requested_mode
    text = " ".join(path.as_posix() for path in scan_roots)
    if "networkaware-scheduler" in text:
        return "networkaware"
    if "loadaware-scheduler" in text:
        return "loadaware"
    if "default-scheduler" in text:
        return "default"
    return "auto"


def iter_yaml_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        if root.name in KUSTOMIZATION_FILENAMES or root.suffix.lower() in YAML_SUFFIXES:
            yield root
        return
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and (path.name in KUSTOMIZATION_FILENAMES or path.suffix.lower() in YAML_SUFFIXES):
            yield path


def load_yaml_documents(path: Path) -> tuple[list[Any], list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    warnings: list[str] = []
    if yaml is None:
        warnings.append("PyYAML is not available; structured checks were skipped for this file.")
        return [], warnings
    try:
        return [document for document in yaml.safe_load_all(text) if document is not None], warnings
    except Exception as exc:
        warnings.append(f"Unable to parse YAML structurally: {exc}")
        return [], warnings


def normalize_references(value: Any) -> list[Any]:
    if isinstance(value, list):
        out: list[Any] = []
        for item in value:
            out.extend(normalize_references(item))
        return out
    if isinstance(value, dict):
        if "path" in value:
            return [value["path"]]
        out: list[Any] = []
        for item in value.values():
            out.extend(normalize_references(item))
        return out
    return [value]


def scan_kustomization_references(path: Path, repo_root: Path) -> list[Finding]:
    relative = repo_relative(path, repo_root)
    documents, warnings = load_yaml_documents(path)
    findings = [
        Finding("warning", "YAML_PARSE_WARNING", relative, warning)
        for warning in warnings
    ]
    for document in documents:
        if not isinstance(document, dict):
            continue
        base = path.parent
        for field in ("resources", "components", "patchesStrategicMerge", "patches"):
            for raw_reference in normalize_references(document.get(field, [])):
                if raw_reference in (None, ""):
                    continue
                reference = str(raw_reference)
                if reference.startswith(("http://", "https://")):
                    continue
                target = (base / reference).resolve()
                if not target.exists():
                    findings.append(Finding(
                        severity="error",
                        code="MISSING_KUSTOMIZE_REFERENCE",
                        path=relative,
                        location=field,
                        message="Kustomization reference does not exist.",
                        value=reference,
                    ))
    return findings


def referenced_kustomization_roots(path: Path) -> list[Path]:
    documents, _warnings = load_yaml_documents(path)
    roots: list[Path] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        base = path.parent
        for field in ("resources", "components", "patchesStrategicMerge", "patches"):
            for raw_reference in normalize_references(document.get(field, [])):
                if raw_reference in (None, ""):
                    continue
                reference = str(raw_reference)
                if reference.startswith(("http://", "https://")):
                    continue
                target = (base / reference).resolve()
                if target.exists():
                    roots.append(target)
    return roots


def expand_scan_roots_with_kustomize_references(scan_roots: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    seen: set[Path] = set()
    queue: list[Path] = list(scan_roots)
    while queue:
        current = queue.pop(0).resolve()
        if current in seen:
            continue
        seen.add(current)
        expanded.append(current)
        kustomizations: list[Path] = []
        if current.is_dir():
            for name in KUSTOMIZATION_FILENAMES:
                candidate = current / name
                if candidate.exists():
                    kustomizations.append(candidate)
            kustomizations.extend(sorted(current.rglob("kustomization.yaml")))
            kustomizations.extend(sorted(current.rglob("kustomization.yml")))
        elif current.name in KUSTOMIZATION_FILENAMES:
            kustomizations.append(current)
        for kustomization in kustomizations:
            for referenced in referenced_kustomization_roots(kustomization):
                if referenced.resolve() not in seen:
                    queue.append(referenced)
    return expanded


def find_hostname_references(value: Any, location: str) -> list[tuple[str, Any]]:
    refs: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_location = f"{location}.{key_text}"
            if key_text == "key" and str(item) in HOSTNAME_SELECTOR_KEYS:
                refs.append((child_location, item))
            if key_text in HOSTNAME_SELECTOR_KEYS:
                refs.append((child_location, item))
            if isinstance(item, str) and item in HOSTNAME_SELECTOR_KEYS:
                refs.append((child_location, item))
            refs.extend(find_hostname_references(item, child_location))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            refs.extend(find_hostname_references(item, f"{location}[{index}]"))
    return refs


def validate_pod_spec(
    pod_spec: dict[str, Any],
    *,
    path: Path,
    repo_root: Path,
    location: str,
    mode: str,
    expected_scheduler_name: str,
    applies_to_localai: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    relative = repo_relative(path, repo_root)

    node_name = pod_spec.get("nodeName")
    if node_name not in (None, ""):
        findings.append(Finding(
            "error", "FORBIDDEN_NODE_NAME", relative,
            "Hard pod placement through spec.nodeName is not allowed in scheduler-aware manifests.",
            f"{location}.nodeName", node_name,
        ))

    node_selector = pod_spec.get("nodeSelector")
    if isinstance(node_selector, dict):
        for key, value in node_selector.items():
            if str(key) in HOSTNAME_SELECTOR_KEYS:
                findings.append(Finding(
                    "error", "FORBIDDEN_HOSTNAME_NODE_SELECTOR", relative,
                    "Hostname-specific nodeSelector is not allowed in scheduler-aware manifests.",
                    f"{location}.nodeSelector.{key}", value,
                ))

    affinity = pod_spec.get("affinity") or {}
    node_affinity = affinity.get("nodeAffinity") if isinstance(affinity, dict) else None
    if node_affinity is not None:
        for loc, value in find_hostname_references(node_affinity, f"{location}.affinity.nodeAffinity"):
            findings.append(Finding(
                "error", "FORBIDDEN_HOSTNAME_NODE_AFFINITY", relative,
                "Hostname-specific nodeAffinity is not allowed in scheduler-aware manifests.",
                loc, value,
            ))

    scheduler_name_present = "schedulerName" in pod_spec and pod_spec.get("schedulerName") not in (None, "")
    scheduler_name = pod_spec.get("schedulerName")
    if applies_to_localai:
        if mode == "default" and scheduler_name_present:
            findings.append(Finding(
                "error", "FORBIDDEN_DEFAULT_SCHEDULER_NAME", relative,
                "Default scheduler variants must leave spec.schedulerName unset.",
                f"{location}.schedulerName", scheduler_name,
            ))
        elif mode in {"loadaware", "networkaware"} and scheduler_name != expected_scheduler_name:
            code = "MISSING_OR_INVALID_LOADAWARE_SCHEDULER_NAME" if mode == "loadaware" else "MISSING_OR_INVALID_NETWORKAWARE_SCHEDULER_NAME"
            label = "Load-aware" if mode == "loadaware" else "Network-aware"
            findings.append(Finding(
                "error", code, relative,
                f"{label} variants must set spec.schedulerName to the configured second scheduler.",
                f"{location}.schedulerName", scheduler_name,
            ))
    return findings


def deployment_name(document: dict[str, Any]) -> str:
    metadata = document.get("metadata") or {}
    return str(metadata.get("name") or "")


def validate_deployment_labels(document: dict[str, Any], *, path: Path, repo_root: Path, location: str) -> list[Finding]:
    findings: list[Finding] = []
    relative = repo_relative(path, repo_root)
    name = deployment_name(document)
    if name not in LOCALAI_DEPLOYMENTS:
        return findings
    metadata_labels = (document.get("metadata") or {}).get("labels") or {}
    selector_labels = (((document.get("spec") or {}).get("selector") or {}).get("matchLabels") or {})
    template_labels = ((((document.get("spec") or {}).get("template") or {}).get("metadata") or {}).get("labels") or {})

    for key in ("group", "app"):
        for label_scope, labels, loc_suffix in [
            ("metadata", metadata_labels, "metadata.labels"),
            ("selector", selector_labels, "spec.selector.matchLabels"),
            ("pod_template", template_labels, "spec.template.metadata.labels"),
        ]:
            if key not in labels or labels.get(key) in (None, ""):
                findings.append(Finding(
                    "error", "MISSING_REQUIRED_LOCALAI_LABEL", relative,
                    f"LocalAI deployments must expose the required {key!r} label in {label_scope} labels.",
                    f"{location}.{loc_suffix}.{key}", labels.get(key),
                ))

    expected_role = LOCALAI_EXPECTED_ROLES.get(name)
    for label_scope, labels, loc_suffix in [
        ("metadata", metadata_labels, "metadata.labels"),
        ("pod_template", template_labels, "spec.template.metadata.labels"),
    ]:
        role_value = labels.get("role")
        if role_value != expected_role:
            findings.append(Finding(
                "error", "MISSING_OR_INVALID_LOCALAI_ROLE_LABEL", relative,
                f"LocalAI deployments must expose the plain role label expected by the network-aware scheduler in {label_scope} labels.",
                f"{location}.{loc_suffix}.role", role_value,
            ))
        benchmark_role_value = labels.get("localai.benchmark/role")
        if benchmark_role_value != expected_role:
            findings.append(Finding(
                "error", "MISSING_OR_INVALID_LOCALAI_BENCHMARK_ROLE_LABEL", relative,
                f"LocalAI deployments must retain the namespaced benchmark role label in {label_scope} labels.",
                f"{location}.{loc_suffix}.localai.benchmark/role", benchmark_role_value,
            ))
    return findings


def validate_service_selector(document: dict[str, Any], *, path: Path, repo_root: Path, location: str) -> list[Finding]:
    findings: list[Finding] = []
    relative = repo_relative(path, repo_root)
    kind = document.get("kind")
    if kind != "Service":
        return findings
    name = str((document.get("metadata") or {}).get("name") or "")
    if name not in LOCALAI_DEPLOYMENTS:
        return findings
    metadata_labels = (document.get("metadata") or {}).get("labels") or {}
    selector = ((document.get("spec") or {}).get("selector") or {})
    for key in ("group", "app"):
        if key not in selector or selector.get(key) in (None, ""):
            findings.append(Finding(
                "error", "MISSING_REQUIRED_SERVICE_SELECTOR_LABEL", relative,
                f"LocalAI services must select workloads through the required {key!r} label.",
                f"{location}.spec.selector.{key}", selector.get(key),
            ))
        if key not in metadata_labels or metadata_labels.get(key) in (None, ""):
            findings.append(Finding(
                "error", "MISSING_REQUIRED_SERVICE_METADATA_LABEL", relative,
                f"LocalAI services must expose the required {key!r} metadata label for traceability.",
                f"{location}.metadata.labels.{key}", metadata_labels.get(key),
            ))
    expected_role = LOCALAI_EXPECTED_ROLES.get(name)
    if metadata_labels.get("role") != expected_role:
        findings.append(Finding(
            "error", "MISSING_OR_INVALID_SERVICE_ROLE_LABEL", relative,
            "LocalAI services must expose the plain role metadata label expected by network-aware observability checks.",
            f"{location}.metadata.labels.role", metadata_labels.get("role"),
        ))
    return findings


def validate_document(
    document: Any,
    *,
    path: Path,
    repo_root: Path,
    result: ValidationResult,
    document_index: int,
    source: str,
) -> None:
    if not isinstance(document, dict):
        return
    kind = str(document.get("kind") or "")
    location = f"$[{document_index}]"
    applies_to_localai = kind == "Deployment" and deployment_name(document) in LOCALAI_DEPLOYMENTS
    if applies_to_localai:
        result.localai_deployments_seen += 1
        if source == "rendered":
            result.rendered_localai_deployments_seen += 1
        result.findings.extend(validate_deployment_labels(document, path=path, repo_root=repo_root, location=location))
    if kind == "Deployment":
        pod_spec = (((document.get("spec") or {}).get("template") or {}).get("spec") or {})
        if isinstance(pod_spec, dict):
            result.findings.extend(validate_pod_spec(
                pod_spec,
                path=path,
                repo_root=repo_root,
                location=f"{location}.spec.template.spec",
                mode=result.mode,
                expected_scheduler_name=result.expected_scheduler_name,
                applies_to_localai=applies_to_localai,
            ))
    if kind == "Pod":
        pod_spec = document.get("spec") or {}
        if isinstance(pod_spec, dict):
            result.findings.extend(validate_pod_spec(
                pod_spec,
                path=path,
                repo_root=repo_root,
                location=f"{location}.spec",
                mode=result.mode,
                expected_scheduler_name=result.expected_scheduler_name,
                applies_to_localai=True,
            ))
    result.findings.extend(validate_service_selector(document, path=path, repo_root=repo_root, location=location))


def validate_file(path: Path, repo_root: Path, result: ValidationResult, source: str = "source") -> None:
    result.source_files_scanned += 1
    relative = repo_relative(path, repo_root)
    try:
        documents, warnings = load_yaml_documents(path)
    except Exception as exc:
        result.findings.append(Finding("error", "READ_ERROR", relative, f"Unable to read file: {exc}"))
        return
    for warning in warnings:
        result.findings.append(Finding("warning", "YAML_PARSE_WARNING", relative, warning))
    result.yaml_documents_scanned += len(documents)
    for index, document in enumerate(documents):
        validate_document(document, path=path, repo_root=repo_root, result=result, document_index=index, source=source)
    if path.name in KUSTOMIZATION_FILENAMES:
        result.kustomization_files_scanned += 1
        result.findings.extend(scan_kustomization_references(path, repo_root))


def find_kustomize_tool() -> list[str] | None:
    kustomize = shutil.which("kustomize")
    if kustomize:
        return [kustomize, "build"]
    kubectl = shutil.which("kubectl")
    if kubectl:
        return [kubectl, "kustomize"]
    return None


def discover_compositions(scan_roots: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for root in scan_roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("kustomization.yaml")) + sorted(root.rglob("kustomization.yml"))
        for candidate in candidates:
            if candidate.is_dir():
                kustomization = candidate / "kustomization.yaml"
            elif candidate.name in KUSTOMIZATION_FILENAMES:
                kustomization = candidate
            else:
                continue
            if not kustomization.exists():
                continue
            resolved = kustomization.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(resolved)
    return result


def render_composition(kustomization: Path, repo_root: Path, command_prefix: list[str]) -> tuple[Path | None, str | None]:
    output_dir = Path(tempfile.mkdtemp(prefix="resource-aware-scheduler-render-"))
    output_path = output_dir / f"{kustomization.parent.name}.rendered.yaml"
    command = command_prefix + [str(kustomization.parent)]
    try:
        process = subprocess.run(command, cwd=str(repo_root), check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as exc:
        return None, f"Unable to render {repo_relative(kustomization, repo_root)}: {exc}"
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or f"exit code {process.returncode}"
        return None, f"Unable to render {repo_relative(kustomization, repo_root)}: {message}"
    output_path.write_text(process.stdout, encoding="utf-8")
    return output_path, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate scheduler-aware LocalAI manifests for default, load-aware, and network-aware variants.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--scan-root", action="append", default=None)
    parser.add_argument("--mode", choices=["auto", "default", "loadaware", "networkaware"], default="auto")
    parser.add_argument("--expected-scheduler-name", default="scheduler-plugins-scheduler")
    parser.add_argument("--rendered-manifest", action="append", default=None)
    parser.add_argument("--render-kustomize", action="store_true")
    parser.add_argument("--require-render", action="store_true")
    parser.add_argument("--source-only", action="store_true", help="Allow source-only validation without rendered manifests. This is intended for quick local linting only.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.source_only and not args.rendered_manifest:
        args.render_kustomize = True
        args.require_render = True
    return args


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root(args.repo_root)
    scan_roots = [resolve_path(value, repo_root) for value in (args.scan_root or ["infra/k8s/compositions/resource-aware-scheduler"])]
    mode = infer_mode(scan_roots, args.mode)
    result = ValidationResult(repo_root=repo_root, scan_roots=scan_roots, mode=mode, expected_scheduler_name=args.expected_scheduler_name)

    if mode == "auto":
        result.findings.append(Finding(
            "warning",
            "SCHEDULER_MODE_NOT_INFERRED",
            ".",
            "Scheduler mode could not be inferred from the scan root; only generic placement and label checks will be applied.",
        ))

    for root in scan_roots:
        if not root.exists():
            result.findings.append(Finding("error", "SCAN_ROOT_NOT_FOUND", repo_relative(root, repo_root), "Configured scan root does not exist."))
            continue
        for yaml_file in iter_yaml_files(root):
            validate_file(yaml_file, repo_root, result, source="source")

    for rendered_manifest in args.rendered_manifest or []:
        path = resolve_path(rendered_manifest, repo_root)
        if not path.exists():
            result.findings.append(Finding("error", "RENDERED_MANIFEST_NOT_FOUND", repo_relative(path, repo_root), "Rendered manifest does not exist."))
            continue
        if path not in result.rendered_manifest_paths:
            result.rendered_manifest_paths.append(path)
        validate_file(path, repo_root, result, source="rendered")

    if args.render_kustomize:
        result.render_attempted = True
        command_prefix = find_kustomize_tool()
        if command_prefix is None:
            message = "No kustomize-compatible command found. Install kustomize or kubectl to validate rendered manifests."
            if args.require_render:
                result.findings.append(Finding("error", "KUSTOMIZE_TOOL_NOT_FOUND", ".", message))
            else:
                result.render_warnings.append(message)
        else:
            result.render_tool = " ".join(os.path.basename(item) if index == 0 else item for index, item in enumerate(command_prefix))
            for kustomization in discover_compositions(scan_roots):
                rendered_path, warning = render_composition(kustomization, repo_root, command_prefix)
                if warning:
                    if args.require_render:
                        result.findings.append(Finding("error", "KUSTOMIZE_RENDER_ERROR", repo_relative(kustomization, repo_root), warning))
                    else:
                        result.render_warnings.append(warning)
                    continue
                if rendered_path is not None:
                    result.rendered_compositions_scanned += 1
                    result.rendered_manifest_paths.append(rendered_path)
                    validate_file(rendered_path, repo_root, result, source="rendered")

    if args.require_render:
        if not result.render_attempted and not result.rendered_manifest_paths:
            result.findings.append(Finding(
                "error",
                "RENDER_REQUIRED_BUT_NOT_ATTEMPTED",
                ".",
                "Rendered-manifest validation is required, but no rendering was attempted and no rendered manifest was supplied.",
            ))
        if result.rendered_compositions_scanned == 0 and not result.rendered_manifest_paths:
            result.findings.append(Finding(
                "error",
                "RENDER_REQUIRED_BUT_NO_RENDERED_COMPOSITIONS",
                ".",
                "Rendered-manifest validation is required, but no composition was rendered or supplied.",
            ))
        if result.rendered_localai_deployments_seen == 0:
            result.findings.append(Finding(
                "error",
                "NO_RENDERED_LOCALAI_DEPLOYMENTS_SEEN",
                ".",
                "The validator did not inspect any rendered LocalAI Deployment. This would make schedulerName, label and selector checks inconclusive.",
            ))

    report = result.to_dict()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Scheduler-comparison manifest validation")
        print("========================================")
        print(f"Repository root              : {repo_relative(repo_root, repo_root)}")
        print(f"Mode                         : {result.mode}")
        print(f"Expected scheduler name      : {result.expected_scheduler_name}")
        print(f"Scan roots                   : {', '.join(repo_relative(path, repo_root) for path in scan_roots)}")
        print(f"Source files scanned         : {result.source_files_scanned}")
        print(f"YAML documents scanned       : {result.yaml_documents_scanned}")
        print(f"Kustomization files scanned  : {result.kustomization_files_scanned}")
        print(f"LocalAI deployments seen     : {result.localai_deployments_seen}")
        print(f"Rendered LocalAI deployments : {result.rendered_localai_deployments_seen}")
        if result.render_attempted:
            print(f"Rendered compositions scanned: {result.rendered_compositions_scanned}")
            if result.render_tool:
                print(f"Render tool                  : {result.render_tool}")
        if result.render_warnings:
            print("\nRender warnings:")
            for warning in result.render_warnings:
                print(f" - {warning}")
        if result.findings:
            print("\nFindings:")
            for finding in result.findings:
                location = f" ({finding.location})" if finding.location else ""
                print(f" - [{finding.severity.upper()}] {finding.code}: {finding.path}{location}: {finding.message}")
                if finding.value is not None:
                    print(f"   value: {finding.value}")
        print("")
        print("SCHEDULER-COMPARISON MANIFEST VALIDATION PASSED." if result.passed else "SCHEDULER-COMPARISON MANIFEST VALIDATION FAILED.")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
