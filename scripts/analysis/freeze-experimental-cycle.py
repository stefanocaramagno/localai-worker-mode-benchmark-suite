#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file():
                yield item


def directory_digest(root: Path) -> Tuple[int, Optional[str]]:
    if not root.exists():
        return 0, None
    digest = hashlib.sha256()
    count = 0
    for file_path in iter_files(root):
        rel = file_path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(file_path).encode("utf-8"))
        digest.update(b"\0")
        count += 1
    return count, digest.hexdigest()


def repo_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else repo_root / path


def safe_rel(path: Optional[Path], repo_root: Path) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return str(path)


def artifact_record(repo_root: Path, rel_path: str, key: str = "", required: bool = False, description: str = "") -> Dict[str, Any]:
    path = repo_path(repo_root, rel_path)
    record: Dict[str, Any] = {
        "key": key or None,
        "path": rel_path,
        "required": bool(required),
        "description": description or None,
        "exists": bool(path and path.exists()),
        "type": "missing",
    }
    if path is None:
        record["error"] = "empty path"
        return record
    if path.is_file():
        record.update({
            "type": "file",
            "sizeBytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    elif path.is_dir():
        file_count, digest = directory_digest(path)
        record.update({
            "type": "directory",
            "fileCount": file_count,
            "sha256": digest,
        })
    return record


def latest_matching_file(root: Path, pattern: str) -> Optional[Path]:
    if not root.is_dir():
        return None
    candidates = [path for path in root.rglob(pattern) if path.is_file()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: (p.stat().st_mtime_ns, p.as_posix()))[-1]


def resolve_legacy_source(repo_root: Path, key: str, spec: Dict[str, Any], resolved: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    mode = str(spec.get("mode", "fixed")).lower()
    source_type = str(spec.get("type", "file")).lower()
    record: Dict[str, Any] = {
        "key": key,
        "mode": mode,
        "type": source_type,
        "exists": False,
        "resolvedPath": None,
        "description": spec.get("description"),
        "required": True,
    }

    if mode == "fixed":
        path_rel = spec.get("path")
        if not path_rel:
            record["error"] = "fixed source resolution requires path"
            return record
        path = repo_path(repo_root, str(path_rel))
        record["resolvedPath"] = str(path_rel)
    elif mode == "latest":
        root_rel = spec.get("root")
        pattern = spec.get("pattern")
        record["root"] = root_rel
        record["pattern"] = pattern
        if not root_rel or not pattern:
            record["error"] = "latest source resolution requires root and pattern"
            return record
        path = latest_matching_file(repo_path(repo_root, str(root_rel)) or repo_root / str(root_rel), str(pattern))
        if path is None:
            record["error"] = f"no file matched {pattern!r} under {root_rel!r}"
            return record
        record["resolvedPath"] = safe_rel(path, repo_root)
    elif mode == "paired_text":
        paired_key = spec.get("pairedWith")
        paired_record = resolved.get(str(paired_key))
        paired_rel = paired_record.get("resolvedPath") if isinstance(paired_record, dict) else None
        if not paired_rel:
            record["error"] = f"paired source {paired_key!r} has not been resolved"
            return record
        paired_path = repo_path(repo_root, str(paired_rel))
        candidate = paired_path.with_suffix(".txt") if paired_path else None
        if not candidate or not candidate.exists():
            record["error"] = f"paired text artifact does not exist for {paired_rel}"
            record["resolvedPath"] = safe_rel(candidate, repo_root) if candidate else None
            return record
        path = candidate
        record["resolvedPath"] = safe_rel(path, repo_root)
    else:
        record["error"] = f"unsupported source resolution mode: {mode}"
        return record

    path = repo_path(repo_root, str(record["resolvedPath"]))
    if source_type == "file" and path and path.is_file():
        record.update({"exists": True, "sizeBytes": path.stat().st_size, "sha256": sha256_file(path)})
    elif source_type == "directory" and path and path.is_dir():
        file_count, digest = directory_digest(path)
        record.update({"exists": True, "fileCount": file_count, "sha256": digest})
    else:
        record["error"] = f"resolved source is not an existing {source_type}"
    return record


def resolve_legacy_sources(repo_root: Path, cycle: Dict[str, Any]) -> List[Dict[str, Any]]:
    resolution = cycle.get("sourceArtifactResolution")
    if not isinstance(resolution, dict):
        return []
    records: Dict[str, Dict[str, Any]] = {}
    ordered: List[Dict[str, Any]] = []
    for key, spec in resolution.items():
        if not isinstance(spec, dict):
            continue
        record = resolve_legacy_source(repo_root, key, spec, records)
        records[key] = record
        ordered.append(record)
    return ordered


def infer_freeze_profile_path(cycle: Dict[str, Any]) -> str:
    candidates = [
        ((cycle.get("freeze") or {}).get("freezeProfilePath") if isinstance(cycle.get("freeze"), dict) else None),
        ((cycle.get("freezeOutputs") or {}).get("freezeProfilePath") if isinstance(cycle.get("freezeOutputs"), dict) else None),
        ((cycle.get("providerBackedInfrastructure") or {}).get("freezeProfilePath") if isinstance(cycle.get("providerBackedInfrastructure"), dict) else None),
        ((cycle.get("pipelineProfiles") or {}).get("freeze") if isinstance(cycle.get("pipelineProfiles"), dict) else None),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def load_freeze_profile(repo_root: Path, cycle: Dict[str, Any], explicit_profile: str) -> Optional[Dict[str, Any]]:
    profile_ref = explicit_profile.strip() if explicit_profile else infer_freeze_profile_path(cycle)
    if not profile_ref:
        return None
    path = repo_path(repo_root, profile_ref)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"Freeze profile not found: {profile_ref}")
    profile = load_json(path)
    profile["_profilePath"] = safe_rel(path, repo_root)
    return profile


def validate_freeze_cycle_consistency(repo_root: Path, cycle_path: Path, cycle: Dict[str, Any], profile: Dict[str, Any]) -> None:
    cycle_id = str(cycle.get("cycleId") or "").strip()
    profile_cycle_id = str(profile.get("cycleId") or "").strip()
    if cycle_id and profile_cycle_id and cycle_id != profile_cycle_id:
        raise ValueError(
            "Freeze profile/cycle mismatch: "
            f"cycle-config {safe_rel(cycle_path, repo_root)} declares cycleId={cycle_id!r}, "
            f"but freeze profile {profile.get('_profilePath') or '<generated legacy profile>'} declares cycleId={profile_cycle_id!r}. "
            "Use a freeze profile that belongs to the selected cycle configuration."
        )

    declared_cycle_config = profile.get("cycleConfigPath")
    if declared_cycle_config:
        declared_path = repo_path(repo_root, str(declared_cycle_config))
        if declared_path is not None:
            try:
                declared_resolved = declared_path.resolve()
                selected_resolved = cycle_path.resolve()
            except Exception:
                declared_resolved = declared_path
                selected_resolved = cycle_path
            if declared_resolved != selected_resolved:
                raise ValueError(
                    "Freeze profile/cycle-config path mismatch: "
                    f"selected cycle-config is {safe_rel(cycle_path, repo_root)}, "
                    f"but freeze profile {profile.get('_profilePath') or '<generated legacy profile>'} declares "
                    f"cycleConfigPath={declared_cycle_config!r}."
                )


def normalize_artifact_policy(profile: Dict[str, Any]) -> Dict[str, Any]:
    policy = dict(profile.get("artifactPolicy") if isinstance(profile.get("artifactPolicy"), dict) else {})
    top_level_map = {
        "outputRoot": "outputRoot",
        "artifactSnapshotRoot": "artifactSnapshotRoot",
        "cycleLockJsonPath": "cycleLockJson",
        "cycleLockTextPath": "cycleLockText",
        "latestManifestPath": "latestManifestPath",
        "latestTextSummaryPath": "latestTextSummaryPath",
        "manifestSuffix": "manifestSuffix",
        "textSuffix": "textSuffix",
        "writeLatestAliases": "writeLatestAliases",
        "preserveExistingSnapshotByDefault": "preserveExistingSnapshotByDefault",
    }
    for source_key, policy_key in top_level_map.items():
        if policy_key not in policy and source_key in profile:
            policy[policy_key] = profile[source_key]
    if "preserveExistingSnapshotByDefault" not in policy:
        policy["preserveExistingSnapshotByDefault"] = True
    profile["artifactPolicy"] = policy
    return policy


def copy_file_or_directory(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    elif src.is_file():
        shutil.copy2(src, dst)
    else:
        raise FileNotFoundError(str(src))


def has_snapshot_files(root: Path) -> bool:
    return root.exists() and any(item.is_file() for item in root.rglob("*"))


def check_required_references(repo_root: Path, required: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for key, value in required.items():
        if isinstance(value, str):
            records.append(artifact_record(repo_root, value, key=key, required=True))
    return records


def read_completion_status(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for path in [
        ("completionGate", "status"),
        ("evaluation", "completionStatus"),
        ("decision", "completionStatus"),
        ("completionGate", "completionStatus"),
    ]:
        current = payload
        for part in path:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
                break
        if current:
            return str(current)
    return None


def evaluate_completion_gate(repo_root: Path, profile: Dict[str, Any], dry_run: bool, skip_gate: bool) -> Dict[str, Any]:
    policy = profile.get("completionGatePolicy") if isinstance(profile.get("completionGatePolicy"), dict) else {}
    required = bool(policy.get("requiredBeforeFreeze", False))
    manifest_rel = policy.get("manifestPath")
    accepted = [str(item) for item in policy.get("acceptedStatuses", ["completed", "completed_with_unsupported_scenarios"])]
    if skip_gate:
        return {"required": required, "skipped": True, "passed": True, "reason": "explicitly skipped"}
    if not required:
        return {"required": False, "passed": True, "reason": "not required by profile"}
    if not manifest_rel:
        return {"required": True, "passed": bool(dry_run), "reason": "completion gate manifest path not declared", "dryRun": dry_run}
    path = repo_path(repo_root, str(manifest_rel))
    if path is None or not path.is_file():
        return {"required": True, "path": manifest_rel, "exists": False, "passed": bool(dry_run), "reason": "missing completion gate manifest", "dryRun": dry_run}
    try:
        payload = load_json(path)
        status = read_completion_status(payload)
    except Exception as exc:
        return {"required": True, "path": manifest_rel, "exists": True, "passed": False, "reason": str(exc)}
    return {
        "required": True,
        "path": manifest_rel,
        "exists": True,
        "status": status,
        "acceptedStatuses": accepted,
        "passed": status in accepted,
    }


def build_legacy_profile_from_cycle(cycle: Dict[str, Any]) -> Dict[str, Any]:
    cycle_id = str(cycle.get("cycleId") or "C0")
    outputs = cycle.get("freezeOutputs") if isinstance(cycle.get("freezeOutputs"), dict) else {}

    default_cycle_root = f"results/experimental-cycles/{cycle_id}"
    default_freeze_root = f"{default_cycle_root}/freeze"
    default_artifact_root = f"{default_cycle_root}/artifacts"

    cycle_lock_json = outputs.get("cycleLockJson", f"{default_freeze_root}/{cycle_id}-cycle-lock.json")
    cycle_lock_text = outputs.get("cycleLockText", f"{default_freeze_root}/{cycle_id}-cycle-lock.txt")
    output_root = outputs.get("outputRoot") or str(Path(str(cycle_lock_json)).parent.as_posix())
    latest_manifest_path = (
        outputs.get("latestManifestPath")
        or outputs.get("freezeManifestJson")
        or f"{default_freeze_root}/latest-freeze-manifest.json"
    )
    latest_text_summary_path = (
        outputs.get("latestTextSummaryPath")
        or outputs.get("freezeSummaryText")
        or f"{default_freeze_root}/latest-freeze-summary.txt"
    )

    snapshot_sources = [
        {
            "key": "diagnosis",
            "type": "directory",
            "source": f"{default_cycle_root}/diagnosis",
            "destination": "runtime/diagnosis",
            "required": True,
        },
        {
            "key": "completionGate",
            "type": "directory",
            "source": f"{default_cycle_root}/completion-gate",
            "destination": "runtime/completion-gate",
            "required": True,
        },
        {
            "key": "reporting",
            "type": "directory",
            "source": f"{default_cycle_root}/reporting",
            "destination": "runtime/reporting",
            "required": True,
        },
    ]
    required = {}
    for section in [
        cycle.get("pipelineProfiles"),
        {"cycleConfig": f"config/experimental-cycles/{cycle_id}.json"},
        cycle.get("baseline"),
        cycle.get("infrastructureProfile"),
    ]:
        if isinstance(section, dict):
            for key, value in section.items():
                if key.endswith("Path") or key in {"configPath", "reporting", "completionGate", "technicalDiagnosis"}:
                    if isinstance(value, str) and value:
                        required[f"{key}"] = value
    return {
        "schemaVersion": "freeze-profile/v1",
        "freezeProfileId": f"FR_{cycle_id}_LEGACY",
        "profileName": f"{cycle_id} Legacy Freeze Profile",
        "cycleId": cycle_id,
        "cycleConfigPath": f"config/experimental-cycles/{cycle_id}.json",
        "baselineId": (cycle.get("baseline") or {}).get("baselineId") if isinstance(cycle.get("baseline"), dict) else None,
        "artifactPolicy": {
            "outputRoot": output_root,
            "artifactSnapshotRoot": outputs.get("artifactSnapshotRoot", default_artifact_root),
            "cycleLockJson": cycle_lock_json,
            "cycleLockText": cycle_lock_text,
            "latestManifestPath": latest_manifest_path,
            "latestTextSummaryPath": latest_text_summary_path,
            "preserveExistingSnapshotByDefault": True,
            "writeLatestAliases": False,
        },
        "requiredReferences": required,
        "snapshotSources": snapshot_sources,
        "primaryFrozenArtifacts": {
            "reportingManifest": "runtime/reporting/reporting-manifest.json",
            "reportMarkdown": "runtime/reporting/report.md",
            "reportHtml": "runtime/reporting/index.html",
            "scenarioSummaryCsv": "runtime/reporting/scenario-summary.csv",
        },
        "completionGatePolicy": {"requiredBeforeFreeze": False},
        "_legacyMode": True,
    }


def _safe_snapshot_subdirectory(value: Any) -> Optional[Path]:
    text = str(value).strip().replace("\\", "/")
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return None
    if any(part in ("", ".", "..") for part in path.parts):
        return None
    return path


def canonical_snapshot_directories(profile: Dict[str, Any]) -> List[Path]:
    policy = profile.get("artifactPolicy") if isinstance(profile.get("artifactPolicy"), dict) else {}
    configured = policy.get("canonicalDirectories", [])
    if not isinstance(configured, list):
        return []

    result: List[Path] = []
    seen = set()
    for item in configured:
        rel = _safe_snapshot_subdirectory(item)
        if rel is None:
            continue
        key = rel.as_posix()
        if key in seen:
            continue
        seen.add(key)
        result.append(rel)
    return result


def create_snapshot(repo_root: Path, profile: Dict[str, Any], force: bool, dry_run: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    policy = profile.get("artifactPolicy") if isinstance(profile.get("artifactPolicy"), dict) else {}
    artifact_root_rel = str(policy.get("artifactSnapshotRoot", "results/experimental-cycles/C1/artifacts"))
    artifact_root = repo_path(repo_root, artifact_root_rel) or repo_root / artifact_root_rel
    preexisting = has_snapshot_files(artifact_root)
    requested_preserve = bool(policy.get("preserveExistingSnapshotByDefault", True)) and preexisting and not force
    missing_primary_before_rebuild: List[str] = []
    if requested_preserve:
        primary_before_rebuild = resolve_primary_artifacts(repo_root, profile)
        missing_primary_before_rebuild = [
            key
            for key, record in primary_before_rebuild.items()
            if not record.get("exists")
        ]

    preserve = requested_preserve and not missing_primary_before_rebuild
    rebuild_incomplete_snapshot = requested_preserve and bool(missing_primary_before_rebuild)

    records: List[Dict[str, Any]] = []
    copied: List[Dict[str, Any]] = []
    missing_required: List[Dict[str, Any]] = []
    canonical_directories = canonical_snapshot_directories(profile)

    if dry_run:
        mode = "dry_run_snapshot_plan"
    elif preserve:
        mode = "reused_existing_snapshot"
    else:
        if force and preexisting:
            mode = "rebuilt_snapshot"
        elif rebuild_incomplete_snapshot:
            mode = "rebuilt_incomplete_snapshot"
        else:
            mode = "created_snapshot"
        if artifact_root.exists() and (force or rebuild_incomplete_snapshot):
            shutil.rmtree(artifact_root)
        artifact_root.mkdir(parents=True, exist_ok=True)
        for rel_dir in canonical_directories:
            (artifact_root / rel_dir).mkdir(parents=True, exist_ok=True)

    for source in profile.get("snapshotSources", []):
        if not isinstance(source, dict):
            continue
        key = str(source.get("key", ""))
        source_rel = str(source.get("source", ""))
        destination = str(source.get("destination", key or source_rel.replace("/", "_")))
        source_type = str(source.get("type", "file"))
        required = bool(source.get("required", False))
        description = str(source.get("description", ""))
        source_path = repo_path(repo_root, source_rel)
        exists = bool(source_path and source_path.exists())
        record = artifact_record(repo_root, source_rel, key=key, required=required, description=description)
        record.update({"destination": destination, "snapshotType": source_type})

        if exists and source_path:
            dest_path = artifact_root / destination
            if not dry_run and not preserve:
                copy_file_or_directory(source_path, dest_path)
                copied.append({
                    "key": key,
                    "source": source_rel,
                    "destination": safe_rel(dest_path, repo_root),
                    "type": source_type,
                })
            record["frozenPath"] = safe_rel(dest_path, repo_root)
        elif required:
            missing_required.append(record)
        records.append(record)

    file_count, digest = directory_digest(artifact_root)
    return {
        "mode": mode,
        "artifactRoot": artifact_root_rel,
        "dryRun": bool(dry_run),
        "force": bool(force),
        "preexistingSnapshot": bool(preexisting),
        "preservedExistingSnapshot": bool(preserve),
        "rebuildIncompleteSnapshot": bool(rebuild_incomplete_snapshot),
        "missingPrimaryArtifactsBeforeRebuild": missing_primary_before_rebuild,
        "copiedThisRun": False if dry_run or preserve else True,
        "copiedArtifacts": copied,
        "canonicalDirectoryCount": len(canonical_directories),
        "canonicalDirectories": [item.as_posix() for item in canonical_directories],
        "sourceArtifactCount": len(records),
        "missingRequiredSourceArtifactCount": len(missing_required),
        "missingRequiredSourceArtifacts": [item.get("path") for item in missing_required],
        "frozenFileCount": file_count,
        "frozenTreeSha256": digest,
    }, records


def resolve_primary_artifact_spec(repo_root: Path, artifact_root_rel: str, key: str, spec: Any) -> Dict[str, Any]:
    artifact_root = repo_path(repo_root, artifact_root_rel) if artifact_root_rel else None
    artifact_root = artifact_root or repo_root

    if isinstance(spec, str):
        path_rel = f"{artifact_root_rel.rstrip('/')}/{spec.lstrip('/')}" if artifact_root_rel else spec
        record = artifact_record(repo_root, path_rel, key=key, required=False)
        record["resolutionMode"] = "fixed"
        return record

    if not isinstance(spec, dict):
        record = artifact_record(repo_root, artifact_root_rel, key=key, required=False)
        record["resolutionMode"] = "invalid"
        record["error"] = "primary artifact specification must be a string or object"
        return record

    mode = str(spec.get("mode", "fixed")).lower()
    if mode == "fixed":
        rel = str(spec.get("path", "")).strip()
        path_rel = f"{artifact_root_rel.rstrip('/')}/{rel.lstrip('/')}" if artifact_root_rel and rel else rel
        record = artifact_record(repo_root, path_rel, key=key, required=bool(spec.get("required", False)), description=str(spec.get("description", "")))
        record["resolutionMode"] = "fixed"
        return record

    if mode == "latest":
        root_rel = str(spec.get("root", "")).strip()
        pattern = str(spec.get("pattern", "")).strip()
        search_root = artifact_root / root_rel if root_rel else artifact_root
        if not pattern:
            path_rel = f"{artifact_root_rel.rstrip('/')}/{root_rel.rstrip('/')}/" if root_rel else artifact_root_rel
            record = artifact_record(repo_root, path_rel, key=key, required=bool(spec.get("required", False)), description=str(spec.get("description", "")))
            record.update({"resolutionMode": "latest", "error": "latest primary artifact resolution requires pattern"})
            return record
        resolved = latest_matching_file(search_root, pattern)
        if resolved is None:
            unresolved_rel = f"{artifact_root_rel.rstrip('/')}/{root_rel.strip('/')}/{pattern}" if root_rel else f"{artifact_root_rel.rstrip('/')}/{pattern}"
            record = artifact_record(repo_root, unresolved_rel, key=key, required=bool(spec.get("required", False)), description=str(spec.get("description", "")))
            record.update({
                "resolutionMode": "latest",
                "root": safe_rel(search_root, repo_root),
                "pattern": pattern,
                "error": "no primary frozen artifact matched the latest selector",
            })
            return record
        record = artifact_record(repo_root, safe_rel(resolved, repo_root) or str(resolved), key=key, required=bool(spec.get("required", False)), description=str(spec.get("description", "")))
        record.update({
            "resolutionMode": "latest",
            "root": safe_rel(search_root, repo_root),
            "pattern": pattern,
            "resolvedPath": safe_rel(resolved, repo_root),
        })
        return record

    record = artifact_record(repo_root, artifact_root_rel, key=key, required=bool(spec.get("required", False)), description=str(spec.get("description", "")))
    record.update({"resolutionMode": mode, "error": f"unsupported primary artifact resolution mode: {mode}"})
    return record


def resolve_primary_artifacts(repo_root: Path, profile: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    policy = profile.get("artifactPolicy") if isinstance(profile.get("artifactPolicy"), dict) else {}
    root_rel = str(policy.get("artifactSnapshotRoot", ""))
    result: Dict[str, Dict[str, Any]] = {}
    for key, spec in (profile.get("primaryFrozenArtifacts") or {}).items():
        result[key] = resolve_primary_artifact_spec(repo_root, root_rel, str(key), spec)
    return result


def build_manifest(
    repo_root: Path,
    cycle_path: Path,
    cycle: Dict[str, Any],
    profile: Dict[str, Any],
    freeze_id: str,
    snapshot: Dict[str, Any],
    source_records: List[Dict[str, Any]],
    required_reference_records: List[Dict[str, Any]],
    completion_gate: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    primary = resolve_primary_artifacts(repo_root, profile)
    missing_required_refs = [item for item in required_reference_records if item.get("required") and not item.get("exists")]
    missing_required_sources = [item for item in source_records if item.get("required") and not item.get("exists")]
    missing_primary = [key for key, item in primary.items() if not item.get("exists")]

    has_blocking_missing = bool(missing_required_refs or missing_required_sources or (missing_primary and not dry_run))
    completion_passed = bool(completion_gate.get("passed", False))
    freeze_completed = (not dry_run) and completion_passed and not has_blocking_missing

    if dry_run:
        status = "dry_run"
    elif freeze_completed:
        status = "frozen"
    elif not completion_passed:
        status = "failed_completion_gate"
    else:
        status = "incomplete"

    file_count, tree_digest = directory_digest(repo_path(repo_root, str((profile.get("artifactPolicy") or {}).get("artifactSnapshotRoot", ""))) or repo_root)

    return {
        "freeze": {
            "freezeId": freeze_id,
            "freezeProfileId": profile.get("freezeProfileId"),
            "cycleId": cycle.get("cycleId") or profile.get("cycleId"),
            "baselineId": (cycle.get("baseline") or {}).get("baselineId") if isinstance(cycle.get("baseline"), dict) else profile.get("baselineId"),
            "status": status,
            "dryRun": bool(dry_run),
            "createdAtUtc": utc_now(),
            "cycleConfigPath": safe_rel(cycle_path, repo_root),
        },
        "profile": {
            "path": profile.get("_profilePath"),
            "freezeProfileId": profile.get("freezeProfileId"),
            "providerId": profile.get("providerId"),
            "infrastructureProfileId": profile.get("infrastructureProfileId"),
        },
        "cycle": {
            "cycleName": cycle.get("cycleName"),
            "cycleStatus": cycle.get("status"),
            "infrastructureProfile": cycle.get("infrastructureProfile"),
            "clusterLifecycle": cycle.get("clusterLifecycle"),
            "providerBackedInfrastructure": cycle.get("providerBackedInfrastructure"),
        },
        "completionGate": completion_gate,
        "artifactSnapshot": {
            **snapshot,
            "verifiedFrozenFileCount": file_count,
            "verifiedFrozenTreeSha256": tree_digest,
        },
        "references": {
            "requiredReferenceCount": len(required_reference_records),
            "missingRequiredReferenceCount": len(missing_required_refs),
            "missingRequiredReferences": [item.get("path") for item in missing_required_refs],
            "requiredReferences": required_reference_records,
        },
        "sourceArtifacts": {
            "sourceArtifactCount": len(source_records),
            "missingRequiredSourceArtifactCount": len(missing_required_sources),
            "missingRequiredSourceArtifacts": [item.get("path") for item in missing_required_sources],
            "records": source_records,
        },
        "primaryFrozenArtifacts": primary,
        "integrity": {
            "missingPrimaryFrozenArtifactCount": len(missing_primary),
            "missingPrimaryFrozenArtifacts": missing_primary,
            "blockingMissingArtifactCount": len(missing_required_refs) + len(missing_required_sources) + (0 if dry_run else len(missing_primary)),
            "completed": freeze_completed,
        },
        "governance": profile.get("governance", {}),
    }


def write_summary(path: Path, manifest: Dict[str, Any]) -> None:
    freeze = manifest.get("freeze", {})
    profile = manifest.get("profile", {})
    completion = manifest.get("completionGate", {})
    snapshot = manifest.get("artifactSnapshot", {})
    refs = manifest.get("references", {})
    sources = manifest.get("sourceArtifacts", {})
    integrity = manifest.get("integrity", {})
    lines = [
        "=============================================",
        " Experimental Cycle Freeze",
        "=============================================",
        f"Freeze ID                         : {freeze.get('freezeId')}",
        f"Cycle ID                          : {freeze.get('cycleId')}",
        f"Baseline ID                       : {freeze.get('baselineId')}",
        f"Status                            : {freeze.get('status')}",
        f"Dry run                           : {freeze.get('dryRun')}",
        f"Created at UTC                    : {freeze.get('createdAtUtc')}",
        f"Freeze profile                    : {profile.get('freezeProfileId')}",
        f"Infrastructure profile            : {profile.get('infrastructureProfileId')}",
        f"Provider                          : {profile.get('providerId')}",
        f"Completion gate status            : {completion.get('status')}",
        f"Completion gate passed            : {completion.get('passed')}",
        f"Snapshot mode                     : {snapshot.get('mode')}",
        f"Artifact snapshot root            : {snapshot.get('artifactRoot')}",
        f"Snapshot file count               : {snapshot.get('verifiedFrozenFileCount')}",
        f"Snapshot tree SHA-256             : {snapshot.get('verifiedFrozenTreeSha256')}",
        f"Required references               : {refs.get('requiredReferenceCount')}",
        f"Missing required references       : {refs.get('missingRequiredReferenceCount')}",
        f"Source artifacts                  : {sources.get('sourceArtifactCount')}",
        f"Missing required source artifacts : {sources.get('missingRequiredSourceArtifactCount')}",
        f"Missing primary frozen artifacts  : {integrity.get('missingPrimaryFrozenArtifactCount')}",
        f"Blocking missing artifacts        : {integrity.get('blockingMissingArtifactCount')}",
        "",
        "Primary frozen artifacts",
        "------------------------",
    ]
    primary = manifest.get("primaryFrozenArtifacts") or {}
    if primary:
        for key, record in primary.items():
            lines.append(f"- {key}: {record.get('path')} (exists={record.get('exists')})")
    else:
        lines.append("- None")

    lines.extend(["", "Missing required references", "---------------------------"])
    missing_refs = refs.get("missingRequiredReferences") or []
    lines.extend([f"- {item}" for item in missing_refs] if missing_refs else ["- None"])

    lines.extend(["", "Missing required source artifacts", "---------------------------------"])
    missing_sources = sources.get("missingRequiredSourceArtifacts") or []
    lines.extend([f"- {item}" for item in missing_sources] if missing_sources else ["- None"])

    write_text(path, "\n".join(lines) + "\n")


def write_aliases(repo_root: Path, profile: Dict[str, Any], manifest_path: Path, summary_path: Path) -> None:
    policy = profile.get("artifactPolicy") if isinstance(profile.get("artifactPolicy"), dict) else {}
    if not bool(policy.get("writeLatestAliases", False)):
        return
    latest_manifest = repo_path(repo_root, policy.get("latestManifestPath"))
    latest_summary = repo_path(repo_root, policy.get("latestTextSummaryPath"))
    if latest_manifest:
        latest_manifest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest_path, latest_manifest)
    if latest_summary:
        latest_summary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(summary_path, latest_summary)


def run_freeze(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    cycle_path = repo_path(repo_root, args.cycle_config)
    if cycle_path is None or not cycle_path.is_file():
        raise FileNotFoundError(f"Cycle configuration not found: {args.cycle_config}")

    cycle = load_json(cycle_path)
    profile = load_freeze_profile(repo_root, cycle, args.profile_config)
    if profile is None:
        profile = build_legacy_profile_from_cycle(cycle)

    validate_freeze_cycle_consistency(repo_root, cycle_path, cycle, profile)

    policy = normalize_artifact_policy(profile)
    if args.output_root:
        policy["outputRoot"] = args.output_root
    if getattr(args, "write_latest_aliases", False):
        policy["writeLatestAliases"] = True
    profile["artifactPolicy"] = policy

    freeze_id = args.freeze_id.strip() if args.freeze_id else f"{profile.get('freezeProfileId', 'FR')}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output_root = repo_path(repo_root, policy.get("outputRoot", "results/experimental-cycles/C1/freeze")) or repo_root / "results/experimental-cycles/C1/freeze"
    manifest_suffix = str(policy.get("manifestSuffix", "_freeze_manifest.json"))
    text_suffix = str(policy.get("textSuffix", "_freeze_summary.txt"))

    manifest_path = repo_path(repo_root, policy.get("cycleLockJson")) if policy.get("cycleLockJson") else output_root / f"{freeze_id}{manifest_suffix}"
    summary_path = repo_path(repo_root, policy.get("cycleLockText")) if policy.get("cycleLockText") else output_root / f"{freeze_id}{text_suffix}"
    timestamped_manifest_path = output_root / f"{freeze_id}{manifest_suffix}"
    timestamped_summary_path = output_root / f"{freeze_id}{text_suffix}"

    required_records = check_required_references(repo_root, profile.get("requiredReferences") if isinstance(profile.get("requiredReferences"), dict) else {})
    completion = evaluate_completion_gate(repo_root, profile, args.dry_run, args.skip_completion_gate)
    snapshot, source_records = create_snapshot(repo_root, profile, args.force, args.dry_run)
    manifest = build_manifest(repo_root, cycle_path, cycle, profile, freeze_id, snapshot, source_records, required_records, completion, args.dry_run)

    write_json(manifest_path, manifest)
    write_summary(summary_path, manifest)
    if timestamped_manifest_path != manifest_path:
        write_json(timestamped_manifest_path, manifest)
    if timestamped_summary_path != summary_path:
        write_summary(timestamped_summary_path, manifest)

    write_aliases(repo_root, profile, manifest_path, summary_path)

    print(f"Cycle {manifest['freeze']['cycleId']} freeze status: {manifest['freeze']['status']}")
    print(f"JSON manifest : {safe_rel(manifest_path, repo_root)}")
    print(f"Text summary  : {safe_rel(summary_path, repo_root)}")
    print(f"Artifacts     : {snapshot.get('artifactRoot')}")
    print(f"Snapshot mode : {snapshot.get('mode')}")
    print(f"Missing required references: {manifest['references']['missingRequiredReferenceCount']}")
    print(f"Missing required source artifacts: {manifest['sourceArtifacts']['missingRequiredSourceArtifactCount']}")
    print(f"Missing primary frozen artifacts: {manifest['integrity']['missingPrimaryFrozenArtifactCount']}")

    if args.dry_run:
        return 0
    return 0 if manifest["integrity"]["completed"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze experimental-cycle evidence into a cycle-scoped immutable artifact snapshot.")
    parser.add_argument("--repo-root", default=".", help="Repository root directory.")
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C1.json", help="Cycle configuration path relative to the repository root.")
    parser.add_argument("--profile-config", default="", help="Optional freeze profile path. If omitted, the cycle profile is used to resolve it.")
    parser.add_argument("--freeze-id", default="", help="Optional freeze identifier. Defaults to freeze profile plus UTC timestamp.")
    parser.add_argument("--output-root", default="", help="Optional override for the freeze output root.")
    parser.add_argument("--force", action="store_true", help="Rebuild the frozen artifact snapshot even if it already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve inputs and write freeze outputs without copying runtime artifacts or failing on missing runtime evidence.")
    parser.add_argument("--skip-completion-gate", action="store_true", help="Skip completion-gate verification. Use only for controlled dry-runs or recovery operations.")
    parser.add_argument(
        "--write-latest-aliases",
        action="store_true",
        help="Enable writing latest freeze aliases when alias paths are configured. Accepted for CLI consistency with the rest of the pipeline.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        return run_freeze(parse_args())
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
