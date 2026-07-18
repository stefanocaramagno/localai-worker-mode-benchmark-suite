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

CONTROL_PLANE_SELECTOR_KEYS = {
    "node-role.kubernetes.io/control-plane",
    "node-role.kubernetes.io/master",
}

CONTROLLED_PLACEMENT_REFERENCE_TOKENS = (
    "infra/k8s/compositions/topology/",
    "infra/k8s/compositions/tenancy/",
    "infra/k8s/overlays/placement/",
    "compositions/topology/",
    "compositions/tenancy/",
    "overlays/placement/",
    "patch-server-placement",
    "patch-workers-placement",
    "patch-placement",
    "node-placement",
    "colocated-",
    "distributed-",
    "server-separated-",
    "balanced-static-",
    "spread-genai-",
)

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
    rendered_manifest_paths: list[Path] = field(default_factory=list)
    source_files_scanned: int = 0
    yaml_documents_scanned: int = 0
    kustomization_files_scanned: int = 0
    rendered_compositions_scanned: int = 0
    render_attempted: bool = False
    render_tool: str | None = None
    render_warnings: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator": "default-scheduler-manifest-validator",
            "schemaVersion": "default-scheduler-manifest-validation/v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "repoRoot": repo_relative(self.repo_root, self.repo_root),
            "scanRoots": [repo_relative(path, self.repo_root) for path in self.scan_roots],
            "renderedManifestPaths": [repo_relative(path, self.repo_root) for path in self.rendered_manifest_paths],
            "renderAttempted": self.render_attempted,
            "renderTool": self.render_tool,
            "renderWarnings": self.render_warnings,
            "sourceFilesScanned": self.source_files_scanned,
            "yamlDocumentsScanned": self.yaml_documents_scanned,
            "kustomizationFilesScanned": self.kustomization_files_scanned,
            "renderedCompositionsScanned": self.rendered_compositions_scanned,
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
        documents = [document for document in yaml.safe_load_all(text) if document is not None]
        return documents, warnings
    except Exception as exc:
        warnings.append(f"Unable to parse YAML structurally: {exc}")
        return [], warnings


def find_forbidden_in_text(path: Path, text: str, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    relative = repo_relative(path, repo_root)
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("nodeName:"):
            value = stripped.partition(":")[2].strip()
            findings.append(Finding(
                severity="error",
                code="FORBIDDEN_NODE_NAME",
                path=relative,
                location=f"line {line_number}",
                message="Hard pod placement through spec.nodeName is not allowed for default-scheduler manifests.",
                value=value,
            ))
        if any(host_key in stripped for host_key in HOSTNAME_SELECTOR_KEYS):
            findings.append(Finding(
                severity="error",
                code="FORBIDDEN_HOSTNAME_SELECTOR_REFERENCE",
                path=relative,
                location=f"line {line_number}",
                message="Hostname-specific scheduling references are not allowed for default-scheduler manifests.",
                value=stripped,
            ))
    return findings


def traverse_forbidden_fields(value: Any, path: Path, repo_root: Path, location: str = "$") -> list[Finding]:
    findings: list[Finding] = []
    relative = repo_relative(path, repo_root)

    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_location = f"{location}.{key_text}"

            if key_text == "nodeName" and item not in (None, ""):
                findings.append(Finding(
                    severity="error",
                    code="FORBIDDEN_NODE_NAME",
                    path=relative,
                    location=child_location,
                    message="Hard pod placement through spec.nodeName is not allowed for default-scheduler manifests.",
                    value=item,
                ))

            if key_text == "nodeSelector" and isinstance(item, dict):
                for selector_key, selector_value in item.items():
                    selector_key_text = str(selector_key)
                    if selector_key_text in HOSTNAME_SELECTOR_KEYS:
                        findings.append(Finding(
                            severity="error",
                            code="FORBIDDEN_HOSTNAME_NODE_SELECTOR",
                            path=relative,
                            location=f"{child_location}.{selector_key_text}",
                            message="Hostname-specific nodeSelector is not allowed for default-scheduler manifests.",
                            value=selector_value,
                        ))

            if key_text == "nodeAffinity":
                for host_ref in find_hostname_references(item, child_location):
                    findings.append(Finding(
                        severity="error",
                        code="FORBIDDEN_HOSTNAME_NODE_AFFINITY",
                        path=relative,
                        location=host_ref[0],
                        message="Hostname-specific nodeAffinity is not allowed for default-scheduler manifests.",
                        value=host_ref[1],
                    ))

            if key_text in HOSTNAME_SELECTOR_KEYS:
                findings.append(Finding(
                    severity="error",
                    code="FORBIDDEN_HOSTNAME_SELECTOR_KEY",
                    path=relative,
                    location=child_location,
                    message="Hostname-specific selector key is not allowed for default-scheduler manifests.",
                    value=item,
                ))

            findings.extend(traverse_forbidden_fields(item, path, repo_root, child_location))

    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(traverse_forbidden_fields(item, path, repo_root, f"{location}[{index}]"))

    return findings


def find_hostname_references(value: Any, location: str) -> list[tuple[str, Any]]:
    references: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_location = f"{location}.{key_text}"
            if key_text == "key" and str(item) in HOSTNAME_SELECTOR_KEYS:
                references.append((child_location, item))
            if key_text in HOSTNAME_SELECTOR_KEYS:
                references.append((child_location, item))
            if isinstance(item, str) and item in HOSTNAME_SELECTOR_KEYS:
                references.append((child_location, item))
            references.extend(find_hostname_references(item, child_location))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            references.extend(find_hostname_references(item, f"{location}[{index}]"))
    return references


def scan_kustomization_references(path: Path, repo_root: Path) -> list[Finding]:
    if path.name not in KUSTOMIZATION_FILENAMES:
        return []

    findings: list[Finding] = []
    relative = repo_relative(path, repo_root)
    documents, warnings = load_yaml_documents(path)
    for warning in warnings:
        findings.append(Finding(
            severity="warning",
            code="KUSTOMIZATION_PARSE_WARNING",
            path=relative,
            message=warning,
        ))

    referenced_values: list[tuple[str, Any]] = []
    if documents:
        root = documents[0]
        if isinstance(root, dict):
            for field in ("resources", "components", "patches", "patchesStrategicMerge", "bases"):
                raw_value = root.get(field)
                if raw_value is None:
                    continue
                for item in normalize_kustomization_references(raw_value):
                    referenced_values.append((field, item))
    else:
        text = path.read_text(encoding="utf-8-sig")
        referenced_values.extend(("text", item.strip()) for item in text.splitlines() if item.strip().startswith("- "))

    for field, reference in referenced_values:
        reference_text = str(reference).replace("\\", "/").strip()
        if not reference_text:
            continue
        if reference_text.startswith("- "):
            reference_text = reference_text[2:].strip()
        resolved = (path.parent / reference_text).resolve() if not Path(reference_text).is_absolute() else Path(reference_text).resolve()
        combined = f"{reference_text} {repo_relative(resolved, repo_root)}".replace("\\", "/")
        lower_combined = combined.lower()
        for token in CONTROLLED_PLACEMENT_REFERENCE_TOKENS:
            if token in lower_combined:
                findings.append(Finding(
                    severity="error",
                    code="FORBIDDEN_CONTROLLED_PLACEMENT_REFERENCE",
                    path=relative,
                    location=field,
                    message="Kustomization references a controlled-placement overlay, composition or placement patch.",
                    value=reference_text,
                ))
                break
    return findings


def normalize_kustomization_references(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        references: list[Any] = []
        for item in value:
            if isinstance(item, dict):
                if "path" in item:
                    references.append(item["path"])
                elif "target" in item or "patch" in item:
                    if "path" in item:
                        references.append(item["path"])
                else:
                    references.extend(normalize_kustomization_references(item))
            else:
                references.append(item)
        return references
    if isinstance(value, dict):
        if "path" in value:
            return [value["path"]]
        references: list[Any] = []
        for item in value.values():
            references.extend(normalize_kustomization_references(item))
        return references
    return [value]


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
    output_dir = Path(tempfile.mkdtemp(prefix="default-scheduler-render-"))
    output_path = output_dir / f"{kustomization.parent.name}.rendered.yaml"
    command = command_prefix + [str(kustomization.parent)]
    try:
        process = subprocess.run(
            command,
            cwd=str(repo_root),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        return None, f"Unable to render {repo_relative(kustomization, repo_root)}: {exc}"

    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or f"exit code {process.returncode}"
        return None, f"Unable to render {repo_relative(kustomization, repo_root)}: {message}"

    output_path.write_text(process.stdout, encoding="utf-8")
    return output_path, None


def validate_file(path: Path, repo_root: Path, result: ValidationResult) -> None:
    result.source_files_scanned += 1
    relative = repo_relative(path, repo_root)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        result.findings.append(Finding(
            severity="error",
            code="READ_ERROR",
            path=relative,
            message=f"Unable to read file: {exc}",
        ))
        return

    result.findings.extend(find_forbidden_in_text(path, text, repo_root))

    documents, warnings = load_yaml_documents(path)
    for warning in warnings:
        result.findings.append(Finding(
            severity="warning",
            code="YAML_PARSE_WARNING",
            path=relative,
            message=warning,
        ))

    result.yaml_documents_scanned += len(documents)
    for document_index, document in enumerate(documents):
        result.findings.extend(traverse_forbidden_fields(document, path, repo_root, f"$[{document_index}]"))

    if path.name in KUSTOMIZATION_FILENAMES:
        result.kustomization_files_scanned += 1
        result.findings.extend(scan_kustomization_references(path, repo_root))


def validate_rendered_manifest(path: Path, repo_root: Path, result: ValidationResult) -> None:
    if path not in result.rendered_manifest_paths:
        result.rendered_manifest_paths.append(path)
    validate_file(path, repo_root, result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate default-scheduler Kubernetes manifests against hard placement controls."
    )
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to the script-derived root.")
    parser.add_argument(
        "--scan-root",
        action="append",
        default=None,
        help="Manifest root or YAML file to scan. Can be supplied multiple times. Defaults to infra/k8s/compositions/default-scheduler.",
    )
    parser.add_argument(
        "--rendered-manifest",
        action="append",
        default=None,
        help="Rendered YAML manifest to validate. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--render-kustomize",
        action="store_true",
        help="Render discovered kustomizations with kustomize or kubectl kustomize and validate the rendered output.",
    )
    parser.add_argument(
        "--require-render",
        action="store_true",
        help="Fail if --render-kustomize is requested but no rendering tool is available or a composition cannot be rendered.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON validation report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root(args.repo_root)

    scan_roots = [
        resolve_path(value, repo_root)
        for value in (args.scan_root or ["infra/k8s/compositions/default-scheduler"])
    ]

    result = ValidationResult(repo_root=repo_root, scan_roots=scan_roots)

    for root in scan_roots:
        if not root.exists():
            result.findings.append(Finding(
                severity="error",
                code="SCAN_ROOT_NOT_FOUND",
                path=repo_relative(root, repo_root),
                message="Configured scan root does not exist.",
            ))
            continue
        for yaml_file in iter_yaml_files(root):
            validate_file(yaml_file, repo_root, result)

    for rendered_manifest in args.rendered_manifest or []:
        path = resolve_path(rendered_manifest, repo_root)
        if not path.exists():
            result.findings.append(Finding(
                severity="error",
                code="RENDERED_MANIFEST_NOT_FOUND",
                path=repo_relative(path, repo_root),
                message="Rendered manifest does not exist.",
            ))
            continue
        validate_rendered_manifest(path, repo_root, result)

    if args.render_kustomize:
        result.render_attempted = True
        command_prefix = find_kustomize_tool()
        if command_prefix is None:
            message = "No kustomize-compatible command found. Install kustomize or kubectl to validate rendered manifests."
            if args.require_render:
                result.findings.append(Finding(
                    severity="error",
                    code="KUSTOMIZE_TOOL_NOT_FOUND",
                    path=".",
                    message=message,
                ))
            else:
                result.render_warnings.append(message)
        else:
            result.render_tool = " ".join(os.path.basename(item) if index == 0 else item for index, item in enumerate(command_prefix))
            for kustomization in discover_compositions(scan_roots):
                rendered_path, warning = render_composition(kustomization, repo_root, command_prefix)
                if warning:
                    if args.require_render:
                        result.findings.append(Finding(
                            severity="error",
                            code="KUSTOMIZE_RENDER_ERROR",
                            path=repo_relative(kustomization, repo_root),
                            message=warning,
                        ))
                    else:
                        result.render_warnings.append(warning)
                    continue
                if rendered_path is not None:
                    result.rendered_compositions_scanned += 1
                    validate_rendered_manifest(rendered_path, repo_root, result)

    report = result.to_dict()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Default-scheduler manifest validation")
        print("=====================================")
        print(f"Repository root              : {repo_relative(repo_root, repo_root)}")
        print(f"Scan roots                   : {', '.join(repo_relative(path, repo_root) for path in scan_roots)}")
        print(f"Source files scanned         : {result.source_files_scanned}")
        print(f"YAML documents scanned       : {result.yaml_documents_scanned}")
        print(f"Kustomization files scanned  : {result.kustomization_files_scanned}")
        if result.render_attempted:
            print(f"Rendered compositions scanned: {result.rendered_compositions_scanned}")
            if result.render_tool:
                print(f"Render tool                  : {result.render_tool}")
        if result.render_warnings:
            print("")
            print("Render warnings:")
            for warning in result.render_warnings:
                print(f" - {warning}")
        if result.findings:
            print("")
            print("Findings:")
            for finding in result.findings:
                location = f" ({finding.location})" if finding.location else ""
                print(f" - [{finding.severity.upper()}] {finding.code}: {finding.path}{location}: {finding.message}")
                if finding.value is not None:
                    print(f"   value: {finding.value}")
        print("")
        if result.passed:
            print("DEFAULT SCHEDULER MANIFEST VALIDATION PASSED.")
        else:
            print("DEFAULT SCHEDULER MANIFEST VALIDATION FAILED.")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
