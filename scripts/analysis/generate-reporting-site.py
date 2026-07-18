#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_common_helpers():
    import importlib.util

    for parent in Path(__file__).resolve().parents:
        common_dir = parent / "scripts" / "common"
        artifact_paths = common_dir / "artifact_paths.py"
        artifact_portability = common_dir / "artifact_portability.py"
        if artifact_paths.is_file() and artifact_portability.is_file():
            paths_spec = importlib.util.spec_from_file_location("artifact_paths", artifact_paths)
            paths_module = importlib.util.module_from_spec(paths_spec)
            assert paths_spec.loader is not None
            paths_spec.loader.exec_module(paths_module)

            portability_spec = importlib.util.spec_from_file_location("artifact_portability", artifact_portability)
            portability_module = importlib.util.module_from_spec(portability_spec)
            assert portability_spec.loader is not None
            portability_spec.loader.exec_module(portability_module)

            return (
                paths_module.normalize_artifact_payload_for_output,
                paths_module.normalize_artifact_text_for_output,
                portability_module.collect_artifact_portability_violations,
                portability_module.PORTABILITY_EXTENSIONS,
            )
    raise RuntimeError("Unable to locate scripts/common artifact helpers")


(
    normalize_artifact_payload_for_output,
    normalize_artifact_text_for_output,
    collect_artifact_portability_violations,
    PORTABILITY_EXTENSIONS,
) = _load_common_helpers()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a static entry point for cycle-scoped benchmark reports.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--site-config", default="config/reporting/site/REPORTING_SITE.json", help="Reporting-site configuration JSON path.")
    parser.add_argument("--reporting-index", default="", help="Optional reporting index path override.")
    parser.add_argument("--output-root", default="", help="Optional output root override for the static reporting site.")
    parser.add_argument("--site-id", default="", help="Optional reporting-site build identifier.")
    parser.add_argument("--strict", action="store_true", help="Fail when no cycle-scoped report is available.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def resolve_path(repo_root: Path, value: str | None, default: str | None = None) -> Path:
    selected = value if value not in (None, "") else default
    if not selected:
        raise ValueError("Path value is not defined.")
    path = Path(str(selected))
    if path.is_absolute():
        return path
    return repo_root / path


def safe_rel(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_csv_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False}
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows.extend(dict(row) for row in reader)
    measured = sum(1 for row in rows if str(row.get("status") or "").strip() == "measured")
    unsupported = sum(1 for row in rows if str(row.get("status") or "").strip() == "unsupported_under_current_constraints")
    return {
        "available": True,
        "scenarioCount": len(rows),
        "measuredScenarioCount": measured,
        "unsupportedScenarioCount": unsupported,
    }


def copy_tree_filtered(src: Path, dst: Path, exclude_dirs: set[str], exclude_files: set[str]) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in exclude_dirs or item.name in exclude_files:
            continue
        target = dst / item.name
        if item.is_dir():
            copy_tree_filtered(item, target, exclude_dirs, exclude_files)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            suffix = item.suffix.lower()
            if suffix == ".json":
                try:
                    write_json(target, load_json(item))
                except Exception:
                    shutil.copy2(item, target)
            elif suffix in PORTABILITY_EXTENSIONS:
                try:
                    content = item.read_text(encoding="utf-8", errors="replace")
                    write_text(target, content)
                except Exception:
                    shutil.copy2(item, target)
            else:
                shutil.copy2(item, target)


def relative_link(from_file: Path, to_file: Path) -> str:
    return Path(os.path.relpath(to_file, start=from_file.parent)).as_posix()


def rewrite_published_cycle_navigation_links(
    cycle_root: Path,
    site_root: Path,
    *,
    site_index_name: str = "index.html",
    site_report_name: str = "report.md",
) -> list[dict[str, Any]]:
    rewritten: list[dict[str, Any]] = []
    if not cycle_root.exists():
        return rewritten

    replacements_by_target = {
        "../../../reporting/index.html": site_root / site_index_name,
        "../../../reporting/report.md": site_root / site_report_name,
    }

    for path in sorted(cycle_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".md"}:
            continue
        try:
            original = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        updated = original
        applied: list[dict[str, str]] = []
        for source_href, target_file in replacements_by_target.items():
            if source_href in updated:
                replacement = relative_link(path, target_file)
                updated = updated.replace(source_href, replacement)
                applied.append({"from": source_href, "to": replacement})

        if updated != original:
            write_text(path, updated)
            rewritten.append({
                "file": safe_rel(path, site_root),
                "replacements": applied,
            })

    return rewritten


def load_optional_json(repo_root: Path, path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    try:
        path = resolve_path(repo_root, path_value)
        if path.is_file():
            return load_json(path)
    except Exception:
        return {}
    return {}


def _append_unique(values: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _scenario_config_paths_from_profile(profile_payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    scenario_config_files = profile_payload.get("scenarioConfigFiles")
    if isinstance(scenario_config_files, dict):
        for item in scenario_config_files.values():
            if isinstance(item, list):
                paths.extend(str(value) for value in item if value)
            elif item:
                paths.append(str(item))
    elif isinstance(scenario_config_files, list):
        paths.extend(str(value) for value in scenario_config_files if value)

    for field in ("referenceScenarioConfigPath", "referenceScenarioConfig"):
        if profile_payload.get(field):
            paths.append(str(profile_payload[field]))

    reference_by_family = profile_payload.get("referenceScenarioConfigByFamily")
    if isinstance(reference_by_family, dict):
        paths.extend(str(value) for value in reference_by_family.values() if value)

    return _deduplicate_paths(paths)


def _extract_infrastructure_profile_id(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("infrastructureProfileId", "cycleInfrastructureProfileId"):
        value = payload.get(key)
        if value:
            return str(value)
    for key in ("infrastructure", "infrastructureProfile", "providerBackedInfrastructure"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            value = nested.get("infrastructureProfileId") or nested.get("profileId")
            if value:
                return str(value)
    return None


def _collect_infrastructure_profile_ids(
    repo_root: Path,
    profile_ref: dict[str, Any],
    profile_payload: dict[str, Any],
    manifest_payload: dict[str, Any],
    infrastructure_payload: dict[str, Any],
) -> list[str]:
    values: list[str] = []

    scope_tokens = {
        str(profile_ref.get("infrastructureProfileScope") or "").strip(),
        str(profile_payload.get("infrastructureProfileScope") or "").strip(),
        str(profile_payload.get("infrastructureSummaryMode") or "").strip(),
        str((profile_payload.get("infrastructureSummarySemantics") or {}).get("scope") or "").strip(),
    }
    variant_scoped = bool(scope_tokens.intersection({
        "scenario_variant",
        "scenario_variant_scoped",
        "variant_scoped",
        "scenario",
    }))

    if variant_scoped:
        for scenario_path in _scenario_config_paths_from_profile(profile_payload):
            scenario_payload = load_optional_json(repo_root, scenario_path)
            _append_unique(values, _extract_infrastructure_profile_id(scenario_payload))

    for payload in (profile_ref, profile_payload, infrastructure_payload, manifest_payload):
        _append_unique(values, _extract_infrastructure_profile_id(payload))

    return values


def _format_infrastructure_display(values: list[str]) -> str:
    if not values:
        return "—"
    return ", ".join(values)

def html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: Arial, sans-serif; max-width: 1180px; margin: 32px auto; padding: 0 24px; line-height: 1.55; color: #202124; }}
    header {{ border-bottom: 1px solid #d9dce1; margin-bottom: 24px; padding-bottom: 16px; }}
    h1 {{ margin-bottom: 8px; }}
    h2 {{ margin-top: 30px; }}
    .subtitle {{ color: #5f6368; font-size: 1.05rem; }}
    .notice {{ border-left: 4px solid #5f6368; background: #f8f9fa; padding: 12px 16px; margin: 18px 0; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 18px 0; }}
    .card {{ border: 1px solid #d9dce1; border-radius: 8px; padding: 14px; background: #fff; }}
    .card .value {{ font-size: 1.55rem; font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0 28px; font-size: 14px; display: block; overflow-x: auto; }}
    th, td {{ border: 1px solid #d0d0d0; padding: 8px 10px; vertical-align: top; }}
    th {{ background: #f2f2f2; }}
    code {{ background: #f6f6f6; padding: 1px 4px; }}
    a {{ color: #0645ad; }}
    .status-available, .status-missing {{ font-weight: 700; }}
    footer {{ border-top: 1px solid #d9dce1; margin-top: 32px; padding-top: 16px; color: #5f6368; font-size: 13px; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(item)}</th>" for item in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    return "<table><thead><tr>" + head + "</tr></thead><tbody>" + "\n".join(body_rows) + "</tbody></table>"


def link(label: str, href: str | None) -> str:
    if not href:
        return "—"
    return f'<a href="{html.escape(href)}">{html.escape(label)}</a>'


def cycle_sort_key(record: dict[str, Any]) -> tuple[int, str]:
    cycle_id = str(record.get("cycleId") or "")
    if len(cycle_id) > 1 and cycle_id[0].upper() == "C" and cycle_id[1:].isdigit():
        return (int(cycle_id[1:]), cycle_id)
    return (10_000, cycle_id)


def _format_source_pattern(pattern: str, cycle_id: str, profile_id: str) -> str:
    return pattern.format(cycleId=cycle_id, reportingProfileId=profile_id)


def _deduplicate_paths(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _source_candidate_values(profile_ref: dict[str, Any], source_policy: dict[str, Any], source_field: str, fallback_pattern: str, cycle_id: str, profile_id: str) -> list[str]:
    values: list[str] = []
    primary = profile_ref.get(source_field)
    if primary:
        values.append(str(primary))

    for item in profile_ref.get("sourceFallbackRoots") or profile_ref.get("sourceFallbackPaths") or []:
        values.append(str(item))

    for item in profile_ref.get("sourceFallbackPatterns") or []:
        values.append(_format_source_pattern(str(item), cycle_id, profile_id))

    for item in source_policy.get("cycleFallbackRoots") or source_policy.get("fallbackRoots") or []:
        values.append(str(item))

    for item in source_policy.get("cycleFallbackPatterns") or source_policy.get("alternateFallbackPatterns") or []:
        values.append(_format_source_pattern(str(item), cycle_id, profile_id))

    values.append(_format_source_pattern(fallback_pattern, cycle_id, profile_id))
    return _deduplicate_paths(values)


def _select_cycle_source(repo_root: Path, candidate_values: list[str], required_files: list[str]) -> tuple[Path, bool, list[str], list[dict[str, Any]]]:
    checked: list[dict[str, Any]] = []
    first_path: Path | None = None

    for value in candidate_values:
        candidate = resolve_path(repo_root, value)
        if first_path is None:
            first_path = candidate
        missing = [name for name in required_files if not (candidate / name).exists()]
        available = candidate.exists() and not missing
        checked.append({
            "path": safe_rel(candidate, repo_root),
            "exists": candidate.exists(),
            "missingRequiredFiles": missing,
            "available": available,
        })
        if available:
            return candidate, True, [], checked

    source_root = first_path or resolve_path(repo_root, "results/experimental-cycles/UNKNOWN/reporting")
    missing = [name for name in required_files if not (source_root / name).exists()]
    return source_root, False, missing, checked


def build_cycle_records(repo_root: Path, site_config: dict[str, Any], reporting_index: dict[str, Any], output_root: Path) -> list[dict[str, Any]]:
    cycle_dir_name = site_config.get("cyclesDirectoryName", "cycles")
    cycles_root = output_root / cycle_dir_name
    cycles_root.mkdir(parents=True, exist_ok=True)

    source_policy = site_config.get("cycleSourcePolicy") or {}
    required_files = [str(item) for item in source_policy.get("requiredFiles") or ["index.html", "reporting-manifest.json"]]
    source_field = str(source_policy.get("sourceReportDirectoryField") or "outputRoot")
    fallback_pattern = str(source_policy.get("fallbackPattern") or "results/experimental-cycles/{cycleId}/reporting")
    copy_policy = site_config.get("copyPolicy") or {}
    exclude_dirs = {str(item) for item in copy_policy.get("excludeDirectoryNames") or []}
    exclude_files = {str(item) for item in copy_policy.get("excludeFileNames") or []}
    copy_enabled = bool(copy_policy.get("copyCycleReports", True))
    require_portable_reports = bool(copy_policy.get("requirePortableCycleReportsBeforeCopy", True))
    portability_sample_limit = int(copy_policy.get("portabilityViolationSampleLimit", 50))

    records: list[dict[str, Any]] = []
    for profile_ref in reporting_index.get("profiles") or []:
        cycle_id = str(profile_ref.get("cycleId") or "").strip()
        profile_id = str(profile_ref.get("reportingProfileId") or "").strip()
        if not cycle_id:
            continue

        profile_payload = load_optional_json(repo_root, str(profile_ref.get("path") or ""))
        candidate_values = _source_candidate_values(profile_ref, source_policy, source_field, fallback_pattern, cycle_id, profile_id)
        source_root, source_available, missing_required, checked_sources = _select_cycle_source(repo_root, candidate_values, required_files)

        html_source = source_root / "index.html"
        manifest_source = source_root / "reporting-manifest.json"
        report_md_source = source_root / "report.md"
        summary_csv_source = source_root / "scenario-summary.csv"
        target_root = cycles_root / cycle_id

        manifest_payload: dict[str, Any] = {}
        if manifest_source.exists():
            try:
                manifest_payload = load_json(manifest_source)
            except Exception:
                manifest_payload = {}
        reporting_payload = manifest_payload.get("reporting") if isinstance(manifest_payload.get("reporting"), dict) else {}
        infrastructure_payload = manifest_payload.get("infrastructure") if isinstance(manifest_payload.get("infrastructure"), dict) else {}
        provider_payload = manifest_payload.get("provider") if isinstance(manifest_payload.get("provider"), dict) else {}
        summary = read_csv_summary(summary_csv_source)

        copied = False
        published_navigation_rewrites: list[dict[str, Any]] = []
        portability_root = source_root
        if source_available and copy_enabled:
            copy_tree_filtered(source_root, target_root, exclude_dirs, exclude_files)
            published_navigation_rewrites = rewrite_published_cycle_navigation_links(
                target_root,
                output_root,
                site_index_name=str(site_config.get("reportHtmlName") or "index.html"),
                site_report_name=str(site_config.get("reportMarkdownName") or "report.md"),
            )
            copied = True
            portability_root = target_root

        portability_violations, portability_files_scanned = ([], 0)
        if source_available:
            portability_violations, portability_files_scanned = collect_artifact_portability_violations(
                portability_root,
                repo_root,
                portability_sample_limit,
            )
        portability_passed = len(portability_violations) == 0
        publishable = source_available and copy_enabled and copied and (portability_passed or not require_portable_reports)

        effective_missing_required = list(missing_required)
        if source_available and require_portable_reports and not portability_passed:
            effective_missing_required.append("portable_report_package")
            if target_root.exists():
                shutil.rmtree(target_root)

        html_link = f"{cycle_dir_name}/{cycle_id}/index.html" if publishable and (target_root / "index.html").exists() else None
        manifest_link = f"{cycle_dir_name}/{cycle_id}/reporting-manifest.json" if publishable and (target_root / "reporting-manifest.json").exists() else None
        summary_link = f"{cycle_dir_name}/{cycle_id}/scenario-summary.csv" if publishable and (target_root / "scenario-summary.csv").exists() else None
        markdown_link = f"{cycle_dir_name}/{cycle_id}/report.md" if publishable and (target_root / "report.md").exists() else None

        infrastructure_profile_ids = _collect_infrastructure_profile_ids(
            repo_root,
            profile_ref,
            profile_payload,
            manifest_payload,
            infrastructure_payload,
        )
        provider_id = (
            profile_ref.get("providerId")
            or provider_payload.get("providerId")
            or manifest_payload.get("providerId")
        )

        records.append({
            "cycleId": cycle_id,
            "reportingProfileId": profile_id,
            "profilePath": profile_ref.get("path"),
            "role": profile_ref.get("role") or profile_ref.get("family") or profile_ref.get("mode") or "cycle_reporting",
            "baselineId": profile_ref.get("baselineId"),
            "infrastructureProfileId": infrastructure_profile_ids[0] if len(infrastructure_profile_ids) == 1 else None,
            "infrastructureProfileIds": infrastructure_profile_ids,
            "infrastructureProfileDisplay": _format_infrastructure_display(infrastructure_profile_ids),
            "infrastructureProfileScope": profile_ref.get("infrastructureProfileScope") or profile_payload.get("infrastructureSummaryMode"),
            "providerId": provider_id,
            "sourceRoot": safe_rel(source_root, repo_root),
            "publishedRoot": safe_rel(target_root, repo_root) if publishable else None,
            "sourceAvailable": source_available,
            "available": publishable,
            "missingRequiredFiles": effective_missing_required,
            "checkedSourceRoots": checked_sources,
            "portability": {
                "status": "PASS" if portability_passed else "FAIL",
                "requiredForPublication": require_portable_reports,
                "validatedRoot": safe_rel(portability_root, repo_root) if source_available else None,
                "filesScanned": portability_files_scanned,
                "violationCount": len(portability_violations),
                "violations": portability_violations,
            },
            "publishedNavigationRewrites": published_navigation_rewrites,
            "reportingId": reporting_payload.get("reportingId") or manifest_payload.get("reportingId"),
            "createdAtUtc": reporting_payload.get("createdAtUtc") or manifest_payload.get("createdAtUtc"),
            "reportTitle": reporting_payload.get("reportTitle") or profile_ref.get("role") or profile_id,
            "scenarioSummary": summary,
            "links": {
                "htmlReport": html_link,
                "manifest": manifest_link,
                "markdownReport": markdown_link,
                "scenarioSummaryCsv": summary_link,
            },
        })
    return sorted(records, key=cycle_sort_key)


def build_index_html(site_config: dict[str, Any], records: list[dict[str, Any]], created_at: str, site_id: str) -> str:
    presentation = site_config.get("presentation") or {}
    title = str(presentation.get("title") or "LocalAI Worker-Mode Benchmark Results")
    subtitle = str(presentation.get("subtitle") or "Cycle-level benchmark reports across fixed-cluster and provider-backed executions")
    overview = str(presentation.get("overview") or "")
    methodological_note = str(presentation.get("methodologicalNote") or "")
    empty_state = str(presentation.get("emptyStateMessage") or "No cycle-level report is currently available.")

    available_count = sum(1 for item in records if item.get("available"))
    scenario_count = sum((item.get("scenarioSummary") or {}).get("scenarioCount") or 0 for item in records)
    unsupported_count = sum((item.get("scenarioSummary") or {}).get("unsupportedScenarioCount") or 0 for item in records)

    cards = f"""
    <div class=\"cards\">
      <div class=\"card\"><div>Available reports</div><div class=\"value\">{available_count}</div></div>
      <div class=\"card\"><div>Registered cycles</div><div class=\"value\">{len(records)}</div></div>
      <div class=\"card\"><div>Scenario entries</div><div class=\"value\">{scenario_count}</div></div>
      <div class=\"card\"><div>Unsupported entries</div><div class=\"value\">{unsupported_count}</div></div>
    </div>
    """

    if records:
        rows: list[list[str]] = []
        for item in records:
            status_text = "available" if item.get("available") else "unavailable"
            summary = item.get("scenarioSummary") or {}
            infrastructure_display = str(item.get("infrastructureProfileDisplay") or "—")
            infrastructure_cell = "<br>".join(html.escape(part.strip()) for part in infrastructure_display.split(",") if part.strip()) or "—"
            rows.append([
                f"<code>{html.escape(str(item.get('cycleId') or ''))}</code>",
                f"<code>{html.escape(str(item.get('reportingProfileId') or ''))}</code>",
                html.escape(str(item.get("providerId") or "—")),
                infrastructure_cell,
                html.escape(status_text),
                html.escape(str(summary.get("scenarioCount") if summary.get("available") else "—")),
                html.escape(str(summary.get("unsupportedScenarioCount") if summary.get("available") else "—")),
                html.escape(str(item.get("createdAtUtc") or "—")),
                link("Open report", (item.get("links") or {}).get("htmlReport")),
            ])
        cycles_table = table(
            ["Cycle", "Report profile", "Provider", "Infrastructure", "Report availability", "Scenarios", "Unsupported", "Generated at", "Links"],
            rows,
        )
    else:
        cycles_table = f"<div class=\"notice\">{html.escape(empty_state)}</div>"

    missing_rows = []
    for item in records:
        if not item.get("available"):
            missing = item.get("missingRequiredFiles") or []
            missing_rows.append([
                f"<code>{html.escape(str(item.get('cycleId') or ''))}</code>",
                html.escape(str(item.get("sourceRoot") or "")),
                html.escape(", ".join(missing) if missing else "source directory unavailable"),
            ])
    missing_section = ""
    if missing_rows:
        missing_section = "<h2>Unavailable cycle reports</h2>" + table(["Cycle", "Expected source", "Reason"], missing_rows)

    body = f"""
<header>
  <h1>{html.escape(title)}</h1>
  <div class=\"subtitle\">{html.escape(subtitle)}</div>
</header>
<section>
  <p>{html.escape(overview)}</p>
  <div class=\"notice\">{html.escape(methodological_note)}</div>
</section>
{cards}
<section>
  <h2>Cycle report index</h2>
  {cycles_table}
</section>
{missing_section}
<footer>
  <div>Reporting-site ID: <code>{html.escape(site_id)}</code></div>
  <div>Generated at UTC: <code>{html.escape(created_at)}</code></div>
</footer>
"""
    return html_page(title, body)


def build_index_markdown(site_config: dict[str, Any], records: list[dict[str, Any]], created_at: str, site_id: str) -> str:
    presentation = site_config.get("presentation") or {}
    title = str(presentation.get("title") or "LocalAI Worker-Mode Benchmark Results")
    subtitle = str(presentation.get("subtitle") or "Cycle-level benchmark reports across fixed-cluster and provider-backed executions")
    overview = str(presentation.get("overview") or "")
    methodological_note = str(presentation.get("methodologicalNote") or "")
    available_count = sum(1 for item in records if item.get("available"))
    scenario_count = sum((item.get("scenarioSummary") or {}).get("scenarioCount") or 0 for item in records)
    unsupported_count = sum((item.get("scenarioSummary") or {}).get("unsupportedScenarioCount") or 0 for item in records)
    lines = [
        f"# {title}",
        "",
        subtitle,
        "",
        overview,
        "",
        f"**Reporting-site ID:** `{site_id}`",
        f"**Generated at UTC:** `{created_at}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Available reports | {available_count} |",
        f"| Registered cycles | {len(records)} |",
        f"| Scenario entries | {scenario_count} |",
        f"| Unsupported entries | {unsupported_count} |",
        "",
        "## Methodological note",
        "",
        methodological_note,
        "",
        "## Cycle report index",
        "",
        "| Cycle | Report profile | Provider | Infrastructure | Report availability | Scenarios | Unsupported | Generated at | Links |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    if not records:
        lines.append("| n/a | n/a | n/a | n/a | unavailable | 0 | 0 | n/a | n/a |")
    for item in records:
        summary = item.get("scenarioSummary") or {}
        status_text = "available" if item.get("available") else "unavailable"
        html_link = (item.get("links") or {}).get("htmlReport")
        html_cell = f"[Open report]({html_link})" if html_link else "—"
        lines.append("| " + " | ".join([
            f"`{item.get('cycleId') or ''}`",
            f"`{item.get('reportingProfileId') or ''}`",
            str(item.get("providerId") or "—"),
            str(item.get("infrastructureProfileDisplay") or "—"),
            status_text,
            str(summary.get("scenarioCount") if summary.get("available") else "—"),
            str(summary.get("unsupportedScenarioCount") if summary.get("available") else "—"),
            str(item.get("createdAtUtc") or "—"),
            html_cell,
        ]) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    site_config_path = resolve_path(repo_root, args.site_config)
    site_config = load_json(site_config_path)
    reporting_index_path = resolve_path(
        repo_root,
        args.reporting_index or site_config.get("sourceReportingIndexPath"),
        "config/reporting/REPORTING_INDEX.json",
    )
    reporting_index = load_json(reporting_index_path)
    output_root = resolve_path(repo_root, args.output_root or site_config.get("outputRoot"), "results/reporting")

    copy_policy = site_config.get("copyPolicy") or {}
    if bool(copy_policy.get("removeManagedOutputRootBeforeGeneration", True)) and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    created = utc_now()
    site_id = args.site_id.strip() or f"REPORTING_SITE_{utc_stamp(created)}"
    created_at = iso_utc(created)

    records = build_cycle_records(repo_root, site_config, reporting_index, output_root)
    available_records = [item for item in records if item.get("available")]
    if args.strict and not available_records:
        raise FileNotFoundError("No cycle-scoped reporting package is available.")

    index_html_name = str(site_config.get("reportHtmlName") or "index.html")
    markdown_name = str(site_config.get("reportMarkdownName") or "report.md")
    manifest_name = str(site_config.get("siteManifestName") or "reporting-site-manifest.json")
    legacy_manifest_name = str(site_config.get("legacyManifestAliasName") or "")
    nojekyll_name = str(site_config.get("noJekyllFileName") or ".nojekyll")

    index_path = output_root / index_html_name
    markdown_path = output_root / markdown_name
    manifest_path = output_root / manifest_name
    write_text(index_path, build_index_html(site_config, records, created_at, site_id))
    write_text(markdown_path, build_index_markdown(site_config, records, created_at, site_id))
    write_text(output_root / nojekyll_name, "")

    manifest = {
        "reportingSite": {
            "siteId": site_id,
            "createdAtUtc": created_at,
            "status": "generated",
            "outputRoot": safe_rel(output_root, repo_root),
            "siteConfigPath": safe_rel(site_config_path, repo_root),
            "reportingIndexPath": safe_rel(reporting_index_path, repo_root),
        },
        "summary": {
            "registeredCycleCount": len(records),
            "availableCycleReportCount": len(available_records),
            "unavailableCycleReportCount": len(records) - len(available_records),
            "scenarioRowCount": sum((item.get("scenarioSummary") or {}).get("scenarioCount") or 0 for item in records),
            "unsupportedScenarioRowCount": sum((item.get("scenarioSummary") or {}).get("unsupportedScenarioCount") or 0 for item in records),
        },
        "artifacts": {
            "htmlIndex": safe_rel(index_path, repo_root),
            "markdownReport": safe_rel(markdown_path, repo_root),
            "manifest": safe_rel(manifest_path, repo_root),
            "cyclesDirectory": safe_rel(output_root / site_config.get("cyclesDirectoryName", "cycles"), repo_root),
        },
        "cycles": records,
    }
    write_json(manifest_path, manifest)
    if legacy_manifest_name and legacy_manifest_name != manifest_name:
        write_json(output_root / legacy_manifest_name, manifest)

    print("Reporting site generated successfully.")
    print(f"Output directory : {output_root}")
    print(f"HTML index       : {index_path}")
    print(f"Markdown report  : {markdown_path}")
    print(f"Manifest         : {manifest_path}")
    print(f"Available cycles : {len(available_records)} / {len(records)}")


if __name__ == "__main__":
    main()
