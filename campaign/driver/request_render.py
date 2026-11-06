"""Campaign request template + renderer (spec §11.1).

Renders the exact request shape the driver submits for a backlog item.
Unresolved placeholders (missing values, "TODO" leftovers, "<..." angle
brackets) must never be sent, so the renderer validates the output.
"""

from __future__ import annotations

REQUEST_CHAR_LIMIT = 20000

REQUEST_TEMPLATE = """\
Campaign: {campaign_id}
Backlog item: {backlog_id}
Title: {title}
Base commit: {base_commit}
Prerequisites: {prerequisites}

Goal: {goal}

Current contracts: {current_contracts}

Required change: {required_change}

Acceptance: {acceptance}

Allowed paths: {allowed_paths}

Constraints: {constraints}

Evidence expected: {evidence_expected}
"""

REQUIRED_FIELDS: list[str] = [
    "campaign_id",
    "backlog_id",
    "title",
    "base_commit",
    "prerequisites",
    "goal",
    "current_contracts",
    "required_change",
    "acceptance",
    "allowed_paths",
    "constraints",
    "evidence_expected",
]


def _value_after_label(rendered: str, label: str) -> str | None:
    for line in rendered.splitlines():
        if line.startswith(label + ":"):
            return line.split(":", 1)[1].strip()
    return None


def _reject_unresolved(rendered: str) -> None:
    if "TODO" in rendered:
        raise ValueError("rendered request contains unresolved 'TODO' placeholder text")
    labels = [
        "Campaign",
        "Backlog item",
        "Title",
        "Base commit",
        "Prerequisites",
        "Goal",
        "Current contracts",
        "Required change",
        "Acceptance",
        "Allowed paths",
        "Constraints",
        "Evidence expected",
    ]
    for label in labels:
        value = _value_after_label(rendered, label)
        if value is None:
            raise ValueError(f"rendered request is missing the '{label}:' line")
        if "<" in value:
            raise ValueError(
                f"rendered request contains unresolved '<...>' placeholder in '{label}'; "
                "placeholders must never be sent"
            )


def render_request(context: dict) -> str:
    """Fill REQUEST_TEMPLATE; raise ValueError on missing/empty or unresolved
    placeholder values, or when the rendered request exceeds 20000 chars."""
    missing = [field for field in REQUIRED_FIELDS if not str(context.get(field, "")).strip()]
    if missing:
        raise ValueError(f"missing or empty placeholder values for: {', '.join(missing)}")
    rendered = REQUEST_TEMPLATE.format(**{field: str(context[field]).strip() for field in REQUIRED_FIELDS})
    _reject_unresolved(rendered)
    if len(rendered) > REQUEST_CHAR_LIMIT:
        raise ValueError(
            f"rendered request is {len(rendered)} characters; limit is {REQUEST_CHAR_LIMIT}"
        )
    return rendered
