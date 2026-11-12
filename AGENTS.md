# AGENTS.md — DevFoundry coding agent guardrails

These rules apply to every coding task run against this repository. They are
part of the accepted contract; violating them invalidates the run.

## Architecture boundaries

- Modular monolith. HTTP handlers are thin adapters (routing, bounded input,
  error mapping) — business transactions live in domain services with explicit
  identity context. Never implement business rules inside handlers.
- Layers: HTTP adapter -> authentication/authorization -> domain services ->
  SQLite transactions / audit + transactional outbox. Dependencies point one
  way; services never import the HTTP adapter.
- Baseline profile is standard-library Python 3.12 only: no FastAPI, Django,
  Flask, ORM, pip installation, or any new package. SQLite through `sqlite3`
  with foreign keys, explicit transactions, parameterized SQL.
- No network access at runtime, no embedded credentials, no microservices.
  Do not split code into extra packages to inflate file counts.
- `web/` is same-origin HTML, CSS, and ES modules only: no bundler, no npm
  dependency, no CDN, no external font.

## Test locations

- Python tests live in `tests/unit/`, `tests/integration/`, and
  `tests/security/`. Each directory is a regular Python package with
  `__init__.py`; discovery is
  `unittest discover -s tests -p "test_*.py" -t .` and must not silently omit
  nested directories.
- Frontend logic tests live in `tests/js/` named `*.test.mjs`, using
  `node:test` and `node:assert/strict` against pure modules importable in
  Node 22 without DOM emulation.
- Never weaken an accepted test to make a run pass. If a test contradicts the
  spec, surface it in the task report instead of editing the test.

## Protected validation rules

- `check.sh` is the owner-reviewed, fixed validation gate. Never edit,
  reformat, replace, or move it; never move its dispatch into an
  agent-editable helper. It requires Python 3.12 and Node 22.
- The fast gate rejects skipped, expected-failure, and unexpected-success
  tests. Do not add `@unittest.skip`, `xfail`, conditional skips, or empty
  placeholder test bodies.
- A green gate is the completion criterion for a task: run `bash check.sh` in
  the qualified environment (Python 3.12 + Node 22) and report the exact
  output. On machines with older Node, report the honest local result
  (expected failure at the Node-22 check) plus the direct Python/Node test
  runs.

## Data conventions

- Money is integer cents (no floats, no rounding). Quantity conversions are
  explicit; the locked stock fixture in `doc/` uses cents and minutes.
- Timestamps are UTC in RFC3339 Z format with second precision
  (e.g. `2026-11-06T12:00:00Z`); always compare/store UTC, never local time.
- All SQL is parameterized; migrations are append-only numbered SQL files with
  recorded checksums; the application audit is append-only.

## Secrets and contamination

- No secrets, tokens, passwords, private LAN traces, or raw task logs in this
  repository. Configuration shapes live in non-secret example files with
  placeholders, never usable credentials.
- Campaign artifacts (`driver/`, `requests/`, `journal/`, `evidence/`,
  `acceptance/`) belong to the separate campaign directory
  (`../campaign-opsledger-run-001/`, outside this repository) — never create
  them inside this repository.
