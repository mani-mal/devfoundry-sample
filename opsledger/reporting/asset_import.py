"""Validated atomic CSV asset import (T061).

Parses a UTF-8 CSV payload of asset rows, validates the header line and every
data row, then inserts all rows in one transaction: either the whole batch is
committed or nothing is written. Duplicate asset tags inside the payload
surface a conflict before any write; a tag already existing in the
organization surfaces a conflict after which everything is rolled back.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from uuid import uuid4

from opsledger.core.clock import RealClock, format_rfc3339
from opsledger.core.context import require_context, require_owned, scoped_first
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, PermissionDeniedError, ValidationError
from opsledger.core.validation import reject_nul

__all__ = ["IMPORT_LIMITS_MESSAGE", "import_assets"]

_BYTE_LIMIT = 65536
_ROW_LIMIT = 200

IMPORT_LIMITS_MESSAGE = (
    "CSV payload too large: maximum 65536 bytes and 200 data rows per import"
)

_TAG_LIMIT = 64
_NAME_LIMIT = 200

_REQUIRED_HEADER = "asset_tag,name,criticality,purchase_cost_cents"
_UNIQUE_ASSET_TAG_SUFFIX = "UNIQUE constraint failed: assets.organization_id, assets.tag"

_SELECT_SITE_ROW_SQL = "SELECT * FROM sites WHERE id = ?"

_INSERT_ASSET_SQL = (
    "INSERT INTO assets (id, organization_id, site_id, tag, name, "
    "criticality, purchase_cost_cents, version, created_at, updated_at, "
    "archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _require_permission(actor: object, permission: str) -> None:
    """Allow only actors whose role grants the permission."""
    role = getattr(actor, "role", None)
    if role not in ("admin", "supervisor"):
        raise PermissionDeniedError(f"{permission} requires admin or supervisor")


def _parse_csv(csv_text: str) -> tuple[list[str], list[list[str]]]:
    """Return the header cells and the data rows of the payload."""
    reader = csv.reader(io.StringIO(csv_text, newline=""))
    rows = [row for row in reader if row]
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _validate_row(cells: list[str], *, row_number: int) -> dict:
    """Validate one data row and return it; raise with "row <n>" on failure."""
    if len(cells) != 4:
        raise ValidationError(f"row {row_number}: expected 4 cells")
    tag, name, criticality, cost_text = cells
    if not tag.strip() or len(tag) > _TAG_LIMIT:
        raise ValidationError(f"row {row_number}: asset_tag must be 1-64 characters")
    if not all(char in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in tag.strip()):
        raise ValidationError(
            f"row {row_number}: asset_tag must contain only lowercase letters, digits and hyphens"
        )
    reject_nul(tag, label="asset_tag")
    if not name.strip() or len(name) > _NAME_LIMIT:
        raise ValidationError(f"row {row_number}: name must be 1-200 characters")
    reject_nul(name, label="name")
    if criticality not in ("low", "medium", "high"):
        raise ValidationError(f"row {row_number}: criticality must be low, medium, or high")
    if not cost_text or any(character not in "0123456789" for character in cost_text):
        raise ValidationError(f"row {row_number}: purchase_cost_cents must be a non-negative integer")
    return {
        "tag": tag,
        "name": name,
        "criticality": criticality,
        "purchase_cost_cents": int(cost_text),
    }


def import_assets(
    conn: sqlite3.Connection,
    context: object,
    *,
    actor: object,
    site_id: str,
    csv_text: str,
) -> list[dict]:
    """Validate the whole payload, then insert every row in one transaction."""
    _require_permission(actor, "asset.write")
    validated_context = require_context(context)
    if not isinstance(site_id, str) or not site_id.strip():
        raise ValidationError("site_id is required")
    if not isinstance(csv_text, str):
        raise ValidationError("csv_text must be a string")
    if len(csv_text.encode("utf-8")) > _BYTE_LIMIT:
        raise ValidationError(IMPORT_LIMITS_MESSAGE)
    site_row = scoped_first(conn, validated_context, _SELECT_SITE_ROW_SQL, (site_id,))
    require_owned(validated_context, site_row, label="site")
    header, rows = _parse_csv(csv_text)
    if len(rows) > _ROW_LIMIT:
        raise ValidationError(IMPORT_LIMITS_MESSAGE)
    if not rows:
        raise ValidationError("CSV payload must contain at least one data row")
    if ",".join(header) != _REQUIRED_HEADER:
        raise ValidationError("header must be exactly asset_tag,name,criticality,purchase_cost_cents")
    seen_tags: set[str] = set()
    parsed_rows: list[dict] = []
    for row_number, row in enumerate(rows, start=1):
        parsed = _validate_row(row, row_number=row_number)
        if parsed["tag"] in seen_tags:
            raise ConflictError(f"duplicate asset_tag in payload: {parsed['tag']}")
        seen_tags.add(parsed["tag"])
        parsed_rows.append(parsed)
    imported: list[dict] = []
    with transaction(conn) as tx:
        for parsed in parsed_rows:
            asset_id = "ast-" + uuid4().hex
            timestamp_text = format_rfc3339(RealClock().now())
            try:
                tx.execute(
                    _INSERT_ASSET_SQL,
                    (
                        asset_id,
                        validated_context.organization_id,
                        site_id,
                        parsed["tag"],
                        parsed["name"],
                        parsed["criticality"],
                        parsed["purchase_cost_cents"],
                        1,
                        timestamp_text,
                        timestamp_text,
                        None,
                    ),
                )
            except sqlite3.IntegrityError as error:
                if str(error).endswith(_UNIQUE_ASSET_TAG_SUFFIX):
                    raise ConflictError("duplicate asset tag") from error
                raise
            imported.append({"id": asset_id, "tag": parsed["tag"]})
    return imported
