"""Shared bounded-text validation helpers for OpsLedger domain services."""

from __future__ import annotations

from opsledger.core.errors import ValidationError

__all__ = ["reject_nul"]


def reject_nul(value: str, *, label: str) -> str:
    """Raise ValidationError when value contains a NUL byte; return value."""
    if "\x00" in value:
        raise ValidationError(f"{label} must not contain a NUL byte")
    return value
