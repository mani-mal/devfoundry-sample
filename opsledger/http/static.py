"""Static file allowlist for the OpsLedger HTTP adapter (spec §8.3).

Resolves a URL path to a safe file under a root directory (normally ``web/``),
serving only allowlisted file types. Traversal, symlinks, missing files, and
disallowed types are all refused with one identical error shape (404 /
``not_found`` / "static file not found"), so attackers learn nothing from the
response. The router wiring is a later task; this module performs no HTTP
work itself.

Never servable: the repository root, SQLite files, journals, or evidence
directories.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path

from .envelope import InputError

__all__ = [
    "DEFAULT_ALLOWED_TYPES",
    "StaticFile",
    "read_static",
    "resolve_static",
]

DEFAULT_ALLOWED_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}

_NOT_FOUND_STATUS = 404
_NOT_FOUND_CODE = "not_found"


def _not_found() -> InputError:
    return InputError(_NOT_FOUND_STATUS, _NOT_FOUND_CODE, "static file not found")


@dataclass(frozen=True)
class StaticFile:
    """One allowlisted static file: resolved location and content type."""

    absolute_path: str
    content_type: str


def _has_symlink_component(root: Path, candidate: Path) -> bool:
    """True when any component of ``candidate`` below ``root`` is a symlink."""
    try:
        relative_parts = candidate.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def resolve_static(
    root: str | Path,
    url_path: str,
    *,
    allowed_types: dict[str, str] | None = None,
) -> StaticFile:
    """Resolve ``url_path`` to a safe file under ``root`` and return it.

    Rules, in order:

    - Strip the leading "/", collapse "." and ".." segments with
      posixpath.normpath; a path that escapes root after normalization
      (normpath starts with ".." or is absolute) raises InputError with
      status 404, code ``not_found``, message "static file not found".
      Traversal is indistinguishable from a missing file — no leak.
    - NUL bytes and backslashes are rejected the same way.
    - Symlink refusal: if any component of the candidate below root is a
      symlink, or the resolved candidate is not within the resolved root,
      treat as not found.
    - Missing file, a directory, or a suffix not in ``allowed_types``:
      the same InputError.
    """
    types = DEFAULT_ALLOWED_TYPES if allowed_types is None else allowed_types

    if "\x00" in url_path or "\\" in url_path:
        raise _not_found()

    stripped = url_path[1:] if url_path.startswith("/") else url_path
    normalized = posixpath.normpath(stripped)

    if posixpath.isabs(normalized) or normalized == ".." or normalized.startswith("../"):
        raise _not_found()

    if normalized in ("", "."):
        normalized = "index.html"

    root_path = Path(root)
    candidate = root_path / normalized

    if _has_symlink_component(root_path, candidate):
        raise _not_found()

    resolved_root = root_path.resolve()
    resolved_candidate = candidate.resolve()

    if not resolved_candidate.is_relative_to(resolved_root):
        raise _not_found()

    if not resolved_candidate.is_file():
        raise _not_found()

    extension = Path(normalized).suffix
    if extension not in types:
        raise _not_found()

    return StaticFile(
        absolute_path=str(resolved_candidate), content_type=types[extension]
    )


def read_static(static_file: StaticFile, *, max_bytes: int = 1048576) -> bytes:
    """Read the bytes of one allowlisted static file.

    Allowlisted UI files (HTML, CSS, ES modules) stay far below the default
    1 MiB cap. A file larger than ``max_bytes`` is a server-side limit
    violation, so it raises InputError with status 500 and code
    ``internal_error`` (413 / ``body_too_large`` is reserved for request
    bodies). If the file has vanished since resolution, treat as not found
    with the same 404 error shape as ``resolve_static``.
    """
    try:
        data = Path(static_file.absolute_path).read_bytes()
    except (OSError, ValueError):
        raise _not_found()
    if len(data) > max_bytes:
        raise InputError(500, "internal_error", "static file too large")
    return data
