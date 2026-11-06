# Task request template (spec §11.1)

Human-readable mirror of `campaign/driver/request_render.py::REQUEST_TEMPLATE`.
Fill every field; never leave `TODO` or `<...>` placeholder brackets unresolved.

```
Campaign: <campaign_id>
Backlog item: <backlog_id>
Title: <title>
Base commit: <base_commit>
Prerequisites: <prerequisites>

Goal: <goal>

Current contracts: <current_contracts>

Required change: <required_change>

Acceptance: <acceptance>

Allowed paths: <allowed_paths>

Constraints: <constraints>

Evidence expected: <evidence_expected>
```

## Field notes

- `Campaign` — campaign id, e.g. `opsledger-run-001`.
- `Backlog item` — backlog id the task implements.
- `Title` — short imperative title (no newlines).
- `Base commit` — the exact commit hash the attempt starts from.
- `Prerequisites` — accepted prior work the attempt depends on.
- `Goal` — one-paragraph outcome statement.
- `Current contracts` — existing modules/signatures that must not break.
- `Required change` — the change to implement, with paths.
- `Acceptance` — verifiable acceptance criteria (tests, gate).
- `Allowed paths` — the only paths the attempt may edit.
- `Constraints` — guardrails (stdlib-only, parameterized SQL, cents, UTC).
- `Evidence expected` — artifacts the review packet must contain.

The rendered request must not exceed 20000 characters.
