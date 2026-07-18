from __future__ import annotations

import re
from pathlib import Path
from typing import Any

REPOSITORY_MARKER = "localai-worker-mode-benchmark-suite"

REPO_RELATIVE_PREFIXES = (
    "config/",
    "docs/",
    "infra/",
    "load-tests/",
    "results/",
    "scripts/",
    ".github/",
)
LOCAL_PATH_PLACEHOLDER = "<local-path>"

_URL_TOKEN_RE = re.compile(r"(?P<url>[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>|{}]+)")


def infer_repository_root(reference_path: Path | str | None = None) -> Path:
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
    for candidate in candidates:
        if candidate.name == REPOSITORY_MARKER:
            return candidate
    return cwd


def _normalise(value: str) -> str:
    text = str(value).replace("\\", "/")
    text = re.sub(r"^([A-Za-z]:)/+", r"\1/", text)
    return re.sub(r"(?<!:)/{2,}", "/", text)


def _is_url_like(value: str) -> bool:
    text = str(value).strip()
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return False
    return bool(_URL_TOKEN_RE.fullmatch(text))


def _mask_urls(value: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        placeholder = f"__ARTIFACT_URL_TOKEN_{len(replacements)}__"
        replacements[placeholder] = match.group("url")
        return placeholder

    return _URL_TOKEN_RE.sub(replace, value), replacements


def _restore_urls(value: str, replacements: dict[str, str]) -> str:
    result = value
    for placeholder, url in replacements.items():
        result = result.replace(placeholder, url)
    return result


def _repo_root_variants(repo_root: Path) -> set[str]:
    variants: set[str] = set()
    try:
        resolved = repo_root.resolve()
    except Exception:
        resolved = repo_root.absolute()
    for item in {repo_root, resolved}:
        raw = str(item)
        if raw:
            variants.add(raw.rstrip("\\/"))
            variants.add(_normalise(raw).rstrip("/"))
    return {item for item in variants if item}


def _repo_relative(value: str) -> str:
    normalised = _normalise(value).strip()
    while normalised.startswith("./"):
        normalised = normalised[2:]
    return normalised


def _looks_like_repo_relative_path(value: str) -> bool:
    normalised = _repo_relative(value)
    return normalised == "." or normalised.startswith(REPO_RELATIVE_PREFIXES)


def _strip_repository_prefix(path_text: str, repo_root: Path) -> str | None:
    raw = str(path_text).strip()
    if not raw:
        return raw
    if _is_url_like(raw):
        return None
    normalised = _normalise(raw)
    for root_variant in sorted(_repo_root_variants(repo_root), key=len, reverse=True):
        root_norm = _normalise(root_variant).rstrip("/")
        if normalised.lower() == root_norm.lower():
            return "."
        if normalised.lower().startswith((root_norm + "/").lower()):
            return _repo_relative(normalised[len(root_norm) + 1 :])
    looks_like_path = normalised.startswith("/") or bool(re.match(r"^[A-Za-z]:/", normalised))
    marker_with_slash = f"/{REPOSITORY_MARKER}/"
    if looks_like_path and marker_with_slash in normalised:
        return _repo_relative(normalised.split(marker_with_slash, 1)[1])
    marker_suffix = f"/{REPOSITORY_MARKER}"
    if looks_like_path and normalised.endswith(marker_suffix):
        return "."
    if _looks_like_repo_relative_path(normalised):
        return _repo_relative(normalised)
    return None


_REPO_PATH_TOKEN_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[\\/][^\"'\n\r\t<>|{}]*?"
    + re.escape(REPOSITORY_MARKER)
    + r"(?:[\\/][^\"'\n\r\t<>|{} ]*)*)"
)

_REPO_RELATIVE_BACKSLASH_TOKEN_RE = re.compile(
    r"(?P<path>(?:\.\\)?(?:config|docs|infra|load-tests|results|scripts|\.github)\\[^\"'\n\r\t<>|{}]*)"
)

_WINDOWS_ABSOLUTE_TOKEN_RE = re.compile(
    r"(?P<path>(?<![A-Za-z0-9+.-])[A-Za-z]:(?:[\\/][^\"'\n\r\t<>|{} ]+)+)"
)


def _sanitize_local_absolute_path(token: str, repo_root: Path) -> str:
    repo_relative = _strip_repository_prefix(token, repo_root)
    if repo_relative is not None:
        return repo_relative
    normalised = _normalise(token)
    tail = normalised.rstrip("/").split("/")[-1]
    return f"{LOCAL_PATH_PLACEHOLDER}/{tail}" if tail else LOCAL_PATH_PLACEHOLDER


def normalize_artifact_string(value: str, repo_root: Path) -> str:
    if not isinstance(value, str):
        return value

    if _is_url_like(value):
        return value

    stripped = value.strip()
    exact = _strip_repository_prefix(stripped, repo_root)
    if exact is not None and stripped == value:
        return exact
    if exact is not None and stripped != value:
        return value.replace(stripped, exact)

    masked_value, url_replacements = _mask_urls(value)

    def replace_repo_token(match: re.Match[str]) -> str:
        token = match.group("path")
        replacement = _strip_repository_prefix(token, repo_root)
        return replacement if replacement is not None else token

    def replace_repo_relative_backslash(match: re.Match[str]) -> str:
        token = match.group("path")
        return _repo_relative(token)

    def replace_windows_absolute(match: re.Match[str]) -> str:
        token = match.group("path")
        return _sanitize_local_absolute_path(token, repo_root)

    result = _REPO_PATH_TOKEN_RE.sub(replace_repo_token, masked_value)
    result = _REPO_RELATIVE_BACKSLASH_TOKEN_RE.sub(replace_repo_relative_backslash, result)
    result = _WINDOWS_ABSOLUTE_TOKEN_RE.sub(replace_windows_absolute, result)
    result = _restore_urls(result, url_replacements)
    if _looks_like_repo_relative_path(result):
        result = _repo_relative(result)
    return result


def normalize_artifact_payload(value: Any, repo_root: Path | str | None = None) -> Any:
    root = Path(repo_root) if repo_root is not None else infer_repository_root()
    if isinstance(value, dict):
        return {key: normalize_artifact_payload(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_artifact_payload(item, root) for item in value]
    if isinstance(value, tuple):
        return [normalize_artifact_payload(item, root) for item in value]
    if isinstance(value, str):
        return normalize_artifact_string(value, root)
    return value


def normalize_artifact_payload_for_output(value: Any, output_path: Path | str) -> Any:
    return normalize_artifact_payload(value, infer_repository_root(Path(output_path)))


def normalize_artifact_text(value: str, repo_root: Path | str | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else infer_repository_root()
    return normalize_artifact_string(value, root)


def normalize_artifact_text_for_output(value: str, output_path: Path | str) -> str:
    return normalize_artifact_text(value, infer_repository_root(Path(output_path)))
