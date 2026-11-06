"""Offline static preflight checks for the DevFoundry campaign.

This helper performs STATIC/OFFLINE checks only (config shape, expected
directories, bootstrap-repo markers, contamination heuristics). It NEVER
makes network calls. Live preflight (server health, whoami, versions) is
done by the operator with real credentials and recorded in reports/ — never
by this module, which never touches secrets.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

EXPECTED_CAMPAIGN_DIRS: list[str] = [
    "requests",
    "journal",
    "evidence",
    "acceptance",
    "platform_cases",
    "reports",
]

EXPECTED_BOOTSTRAP_FILES: list[str] = ["check.sh", "README.md", "AGENTS.md"]

_SECRET_VALUE_TOKENS = ("token", "password", "secret")
_PLACEHOLDER_KEYS = ("password_source", "devfoundry_email_placeholder")


@dataclass
class PreflightCheck:
    name: str
    observed: str | None
    status: str  # "ok" | "unknown" | "blocker"
    note: str | None = None


def _read_config(config_path: Path) -> dict:
    with open(Path(config_path), encoding="utf-8") as handle:
        return json.load(handle)


def _status_dir(path: Path) -> str:
    return "ok" if path.is_dir() else "unknown"


def collect_static_preflight(config_path: Path, workspace_root: Path) -> list[PreflightCheck]:
    """Static/offline checks against a config.example.json-shape file.

    Never makes network calls; live preflight (server health, whoami,
    versions) is operator-performed with real credentials and recorded in
    reports/.
    """
    checks: list[PreflightCheck] = []
    workspace_root = Path(workspace_root)

    try:
        config = _read_config(Path(config_path))
    except (OSError, json.JSONDecodeError) as error:
        checks.append(
            PreflightCheck(
                name="config readable",
                observed=None,
                status="blocker",
                note=f"cannot read config: {error}",
            )
        )
        return checks

    # (a) devfoundry_url
    url = str(config.get("devfoundry_url", "") or "")
    if url.startswith(("http://", "https://")) and url.strip() == url and len(url) > len("http://"):
        checks.append(
            PreflightCheck(
                name="devfoundry_url",
                observed=url,
                status="ok",
                note="static shape check only; live health/whoami is operator-performed",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="devfoundry_url",
                observed=url or None,
                status="blocker",
                note="devfoundry_url must be a non-empty http(s) URL",
            )
        )

    # (b) password_source placeholder
    password_source = str(config.get("password_source", "") or "")
    if "<" in password_source:
        checks.append(
            PreflightCheck(
                name="password_source",
                observed=password_source,
                status="unknown",
                note="operator must supply secret source; never store in config",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="password_source",
                observed=password_source,
                status="blocker",
                note="password_source must remain a placeholder in config; secrets live operator-side",
            )
        )

    # (c) campaign dirs expected
    campaign_root = workspace_root / "campaign"
    missing_dirs: list[str] = []
    for directory in EXPECTED_CAMPAIGN_DIRS:
        if not (campaign_root / directory).is_dir():
            missing_dirs.append(directory)
    if missing_dirs:
        checks.append(
            PreflightCheck(
                name="campaign dirs",
                observed="missing: " + ", ".join(missing_dirs),
                status="unknown",
                note="expected subdirs absent in campaign/",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="campaign dirs",
                observed="all present: " + ", ".join(EXPECTED_CAMPAIGN_DIRS),
                status="ok",
                note=None,
            )
        )

    # (d) bootstrap repo markers
    workspace_root = Path(workspace_root)
    missing_files = [name for name in EXPECTED_BOOTSTRAP_FILES if not (workspace_root / name).is_file()]
    if "check.sh" in missing_files:
        checks.append(
            PreflightCheck(
                name="bootstrap repo markers",
                observed="missing: " + ", ".join(missing_files) if missing_files else "all present",
                status="blocker",
                note="check.sh (owner-reviewed validation gate) must exist at workspace root",
            )
        )
    elif missing_files:
        checks.append(
            PreflightCheck(
                name="bootstrap repo markers",
                observed="missing: " + ", ".join(missing_files),
                status="unknown",
                note="README.md and AGENTS.md expected at workspace root",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="bootstrap repo markers",
                observed="all present: " + ", ".join(EXPECTED_BOOTSTRAP_FILES),
                status="ok",
                note=None,
            )
        )

    # (e) contamination: no literal non-placeholder secret-looking values
    contaminated: list[str] = []
    for key, value in config.items():
        if not isinstance(value, str):
            continue
        lowered_key = key.lower()
        lowered_value = value.lower()
        looks_secret = any(token in lowered_key or token in lowered_value for token in _SECRET_VALUE_TOKENS)
        is_placeholder_key = any(placeholder in lowered_key for placeholder in _PLACEHOLDER_KEYS)
        is_placeholder_value = "<" in value
        if looks_secret and not is_placeholder_key and not is_placeholder_value:
            contaminated.append(key)
    if contaminated:
        checks.append(
            PreflightCheck(
                name="config contamination",
                observed="secret-looking literal values in: " + ", ".join(contaminated),
                status="blocker",
                note="config must contain placeholders only; never usable credentials",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="config contamination",
                observed="no literal non-placeholder secret-looking values",
                status="ok",
                note=None,
            )
        )

    return checks


def write_preflight_report(checks: list[PreflightCheck], out_path: Path) -> None:
    """Write a markdown report via temporary file + os.replace (atomic)."""
    lines = [
        "# Campaign static preflight report",
        "",
        "| check | observed | status | note |",
        "| --- | --- | --- | --- |",
    ]
    for check in checks:
        observed = (check.observed or "").replace("|", "\\|").replace("\n", " ")
        note = (check.note or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {check.name} | {observed} | {check.status} | {note} |")
    lines.append("")
    out_path = Path(out_path)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(out_path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, out_path)
