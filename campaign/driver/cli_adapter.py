"""Thin DevFoundry CLI/HTTP adapter with DRY-RUN mode.

Builds documented argv arrays (never shell=True) for the `devfoundry` CLI.
In dry_run mode the adapter returns clearly-labelled "fixture" results and
never claims a live task. In live mode it requires an operator-injected
runner callable plus operator authorization and stored credentials; it never
reads or embeds credentials itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SUBMITTED_TASK_MARKER = "Submitted tsk-"
SUBMITTED_TASK_PATTERN = re.compile(r"Submitted (tsk-[0-9a-f]{8,64})\s*·\s*base\s+\S+")
TASK_ID_PATTERN = re.compile(r"^tsk-[0-9a-f]{8,64}$")

DRY_RUN_SUBMIT_LINE = "fixture: dry-run submit (no live task claimed)"


@dataclass
class DryRunResult:
    """Result of a dry-run adapter invocation; always labelled "fixture"."""

    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    label: str = field(default="fixture")


class DevFoundryAdapter:
    """DevFoundry CLI adapter; dry_run by default, live only with injected runner."""

    def __init__(self, base_url: str, adapter_mode: str = "dry_run", runner=None):
        if adapter_mode not in ("dry_run", "live"):
            raise ValueError(f"adapter_mode must be 'dry_run' or 'live'; got {adapter_mode!r}")
        self.base_url = base_url
        self.adapter_mode = adapter_mode
        self.runner = runner

    @staticmethod
    def _validate_string_args(values: dict[str, str]) -> None:
        for name, value in values.items():
            if not isinstance(value, str) or value == "" or not value.strip():
                raise ValueError(f"argument '{name}' must be a non-empty string")
            if "\n" in value or "\r" in value:
                raise ValueError(f"argument '{name}' must not contain a newline")

    @staticmethod
    def build_submit_argv(
        title: str,
        project: str,
        repo: str,
        base: str,
        request_path: str,
        mode: str = "implement",
        autonomy: str = "workspace",
        environment: str = "polyglot",
        preview: bool = False,
    ) -> list[str]:
        """Argument ARRAY following the documented submit pattern (no shell=True)."""
        DevFoundryAdapter._validate_string_args(
            {
                "title": title,
                "project": project,
                "repo": repo,
                "base": base,
                "request_path": request_path,
                "mode": mode,
                "autonomy": autonomy,
                "environment": environment,
            }
        )
        argv = [
            "devfoundry",
            "submit",
            title,
            "--project",
            project,
            "--repo",
            repo,
            "--base",
            base,
            "--mode",
            mode,
            "--autonomy",
            autonomy,
            "--environment",
            environment,
            "--request-file",
            request_path,
        ]
        if preview:
            argv.append("--preview")
        return argv

    @staticmethod
    def build_watch_argv(task_id: str) -> list[str]:
        """Argument ARRAY for watching a task; task_id must be tsk-<8..64 hex>."""
        DevFoundryAdapter._validate_string_args({"task_id": task_id})
        if not TASK_ID_PATTERN.match(task_id):
            raise ValueError(
                f"task_id '{task_id}' must match '^tsk-[0-9a-f]{{8,64}}$' "
                "(unique prefix of at least 8 hex chars after tsk-)"
            )
        return ["devfoundry", "watch", task_id]

    def build_policy_preview_block(
        self,
        mode: str,
        autonomy: str,
        isolation: str,
        allowed: list[str],
        ask: list[str],
        denied: list[str],
        pack: str,
        pack_version: str,
        role: str,
        profile: str,
    ) -> str:
        """Documented policy-preview shape, labelled "fixture" for dry-run use."""
        lines = [
            "fixture: policy preview (simulated CLI reply; no live task claimed)",
            f"  mode: {mode}",
            f"  autonomy: {autonomy}",
            f"  isolation: {isolation}",
            "  allowed:",
        ]
        lines.extend(f"    - {item}" for item in allowed)
        lines.append("  ask:")
        lines.extend(f"    - {item}" for item in ask)
        lines.append("  denied:")
        lines.extend(f"    - {item}" for item in denied)
        lines.extend(
            [
                f"  pack: {pack}",
                f"  pack_version: {pack_version}",
                f"  role: {role}",
                f"  profile: {profile}",
            ]
        )
        return "\n".join(lines) + "\n"

    def submit(
        self,
        title: str,
        project: str,
        repo: str,
        base: str,
        request_path: str,
        mode: str = "implement",
        autonomy: str = "workspace",
        environment: str = "polyglot",
        preview: bool = False,
    ):
        """Dry-run: labelled fixture result, no live task claimed.

        Live: requires an injected runner callable; otherwise raises.
        """
        argv = self.build_submit_argv(
            title,
            project,
            repo,
            base,
            request_path,
            mode=mode,
            autonomy=autonomy,
            environment=environment,
            preview=preview,
        )
        if self.adapter_mode == "dry_run":
            return self._dry_run_submit(argv)
        if self.runner is None:
            raise RuntimeError(
                "live submissions require operator authorization and stored credentials; "
                "adapter runner not configured"
            )
        return self.runner(argv)

    def _dry_run_submit(self, argv: list[str]) -> DryRunResult:
        block = self.build_policy_preview_block(
            mode="implement",
            autonomy="workspace",
            isolation="pod-per-task",
            allowed=["workspace/ edits", "run bash check.sh in validation pod"],
            ask=["nothing; workspace autonomy"],
            denied=["network egress", "git push", "credential access"],
            pack="opsledger-baseline",
            pack_version="1",
            role="implement",
            profile="polyglot",
        )
        return DryRunResult(
            argv=argv,
            exit_code=0,
            stdout=DRY_RUN_SUBMIT_LINE + "\n" + block,
            stderr="",
            label="fixture",
        )


def parse_submitted_task_id(stdout: str) -> str | None:
    """Parse 'Submitted tsk-<hex> · base <branch>'; None when absent.

    Only the "Submitted tsk-" marker yields an ID; a human title mentioning
    tsk- is never treated as a task ID.
    """
    match = SUBMITTED_TASK_PATTERN.search(stdout)
    if match:
        return match.group(1)
    return None
