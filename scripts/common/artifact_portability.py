from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

PORTABILITY_EXTENSIONS = {".json", ".txt", ".md", ".html", ".csv", ".yaml", ".yml"}

URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>|{}]+")

PORTABILITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("windows_user_path", re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]+Users[\\/]")),
    ("windows_appdata_path", re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]+Users[\\/][^\r\n\"']+[\\/]+AppData[\\/]")),
    ("windows_kubectl_path", re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]+kubectl[\\/]")),
    ("windows_absolute_path", re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]+[^\r\n\"'<>|{}]+")),
    ("escaped_windows_separator", re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:\\\\")),
    ("repo_relative_backslash_path", re.compile(r"(?<![A-Za-z0-9._/-])(?:\.\\)?(?:config|docs|infra|load-tests|results|scripts|\.github)\\[^\r\n\"'<>|{}]+")),
]


def resolve_repo_root(reference_path: Path | str | None = None) -> Path:
    candidates: list[Path] = []
    if reference_path is not None:
        ref = Path(reference_path)
        try:
            resolved = ref.resolve()
        except Exception:
            resolved = ref.absolute()
        candidates.extend([resolved, *resolved.parents])
        if resolved.suffix:
            candidates.extend([resolved.parent, *resolved.parent.parents])
    try:
        cwd = Path.cwd().resolve()
    except Exception:
        cwd = Path.cwd().absolute()
    candidates.extend([cwd, *cwd.parents])
    for candidate in candidates:
        if (candidate / "config").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    return cwd


def resolve_root(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix().replace("\\", "/")


def iter_candidate_files(root: Path, extensions: Iterable[str] = PORTABILITY_EXTENSIONS):
    allowed = {item.lower() for item in extensions}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in allowed:
            yield path


def collect_artifact_portability_violations(
    root: Path | str,
    repo_root: Path | str,
    limit: int | None = None,
    extensions: Iterable[str] = PORTABILITY_EXTENSIONS,
) -> tuple[list[dict[str, Any]], int]:
    repo_root_path = Path(repo_root).resolve()
    root_path = Path(root).resolve()
    violations: list[dict[str, Any]] = []
    files_scanned = 0

    if not root_path.exists():
        return violations, files_scanned

    for path in iter_candidate_files(root_path, extensions=extensions):
        files_scanned += 1
        relative_file = repo_relative(path, repo_root_path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            violations.append({"file": relative_file, "line": 0, "pattern": "unreadable_file", "sample": str(exc)})
            if limit is not None and len(violations) >= limit:
                return violations[:limit], files_scanned
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            line_without_urls = URL_RE.sub("<url>", line)
            for pattern_id, regex in PORTABILITY_PATTERNS:
                if regex.search(line_without_urls):
                    sample = line.strip()
                    if len(sample) > 220:
                        sample = sample[:220] + "..."
                    violations.append({"file": relative_file, "line": line_number, "pattern": pattern_id, "sample": sample})
                    if limit is not None and len(violations) >= limit:
                        return violations[:limit], files_scanned
    return violations, files_scanned


def build_result(repo_root: Path, artifact_root: Path, limit: int | None = None) -> dict[str, Any]:
    violations, files_scanned = collect_artifact_portability_violations(artifact_root, repo_root, limit=limit)
    return {
        "status": "PASS" if not violations else "FAIL",
        "repositoryRoot": ".",
        "artifactRoot": repo_relative(artifact_root, repo_root),
        "filesScanned": files_scanned,
        "violationCount": len(violations),
        "violations": violations,
    }


def print_text_result(result: dict[str, Any], display_limit: int = 40) -> None:
    violations = result.get("violations") or []
    print("=============================================")
    print(" Artifact Portability Validation")
    print("=============================================")
    print(f"Artifact root   : {result.get('artifactRoot')}")
    print(f"Files scanned   : {result.get('filesScanned')}")
    print(f"Violations      : {result.get('violationCount')}")
    print(f"Overall result  : {result.get('status')}")
    if violations:
        print("\nDetected non-portable local path references:")
        for item in violations[:display_limit]:
            print(f" - {item['file']}:{item['line']} [{item['pattern']}] {item['sample']}")
        if len(violations) > display_limit:
            print(f" - ... plus {len(violations) - display_limit} additional violations")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated artifacts for non-portable local path references.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--results-root", default="results", help="Artifact root to validate.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of violations to retain. 0 means unlimited.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    artifact_root = resolve_root(repo_root, args.results_root).resolve()
    if not artifact_root.exists():
        raise FileNotFoundError(f"Artifact root not found: {artifact_root}")
    limit = args.limit if args.limit and args.limit > 0 else None
    result = build_result(repo_root, artifact_root, limit=limit)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_text_result(result)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
