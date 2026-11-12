# OpsLedger

## Changes from OpenCode (bootstrap, November 6, 2026)

> Root of this repository was the DevFoundry lab seed repository (`# Sample — a seed repository for DevFoundry lab tests`), merged with the OpsLedger bootstrap per owner instruction.

This repository received its initial OpsLedger bootstrap from the OpenCode
session running the DevFoundry campaign `opsledger-run-001`. The changes in
this commit are:

- **`check.sh`** — new fixed, owner-reviewed validation gate (byte-exact from
  the project spec §9.2): compiles all `opsledger` sources, runs the discovered
  `unittest` suite, rejects skipped/expected-failure tests, requires
  Python 3.12 + Node 22, checks `web/**/*.mjs` with `node --check`, and runs
  `tests/js/*.test.mjs` with `node --test`. Do not edit it; feature tasks add
  tests in directories it already discovers.
- **`opsledger/`** — new minimal package: `__init__.py` (version 0.1.0) and
  `__main__.py` (argparse CLI with `migrate`, `serve`, `seed`, `reconcile`,
  `backup`, `restore`, `diagnostics`). Only `diagnostics` is functional at
  bootstrap; the rest are stubs (exit 2). No feature code is hidden here.
- **`tests/`** — new test packages `tests/unit/`, `tests/integration/`,
  `tests/security/` (each a regular package with `__init__.py` so Python 3.12
  discovery cannot silently omit them), with real unit tests for the CLI smoke,
  `--help`, stub exit codes, and package version; `tests/js/format.test.mjs`
  for the `web/js/app.mjs` module using `node:test`.
- **`web/`** — new bootstrap UI shell: `index.html`, `css/styles.css`, and
  `js/app.mjs` (DOM-free at import, importable in Node without DOM emulation).
- **`docs/architecture.md`** — modular-monolith architecture notes and layout.
- **`AGENTS.md`** — guardrails for DevFoundry coding agents (architecture
  boundaries, test locations, protected validation rules, data conventions).
- **`README.md`** — this file, with quick start, test gate, and lab limitations.
- **`doc/`** — the project specification (`DevFoundry_Large_Scale_OpenCode_Project.md`)
  and the DevFoundry campaign docs supplied alongside the workspace.

Campaign scaffolding (driver code, journal, request files, evidence) lives
outside the product tree in a separate local directory
(`../campaign-opsledger-run-001/`, owner decision 2026-11-12); it is not part
of the public application history. No credentials, tokens, or LAN traces are
committed.

Legacy tracked files from a previous project (an older dev-foundry build:
`.nx/`, `Dockerfile*`, `packages/`, `docs/tech`, `test-app/`, and related
paths) were already deleted in the working tree and those deletions are
included in this commit, leaving a clean OpsLedger-only tree.

OpsLedger is a multi-organization operations system for sites, equipment, work
orders, spare parts, purchase requests, incident follow-up, and reporting.
Every record belongs to an organization; authorization, search, dashboards,
exports, and audit events are scoped to the caller's membership. The baseline
profile is an installation-free lab benchmark: Python 3.12 standard library,
SQLite, HTML/CSS/ES modules, and nothing else.

## Quick start (no installation)

```bash
python3 -m opsledger diagnostics
python3 -m opsledger --help
python3 -m opsledger migrate   # stub at bootstrap: prints notice, exit 2
```

CLI subcommands: `migrate`, `serve`, `seed`, `reconcile`, `backup`, `restore`,
`diagnostics`. At bootstrap only `diagnostics` is functional; the other
subcommands print "not implemented in bootstrap" to stderr and exit 2. Feature
work lands through DevFoundry tasks, not through this bootstrap.

## Tests

```bash
bash check.sh
```

`check.sh` is the fixed, owner-reviewed validation gate. It compiles all
`opsledger` Python sources, runs the discovered `unittest` suite, checks that
every `web/**/*.mjs` parses with `node --check`, and runs `tests/js/*.test.mjs`
with `node --test`. The qualified environment requires **Python 3.12** and
**Node 22**; on machines with older Node (e.g. 18) the gate fails at the
Node-22 check after all Python steps have passed, which is expected.

Direct runs during development:

```bash
python3 -m unittest discover -s tests -p "test_*.py" -t . -v
node --test tests/js/format.test.mjs
node --check web/js/app.mjs
```

## Lab limitations

- Standard-library-only baseline: no web framework, no ORM, no pip packages.
- The HTTP adapter wraps `http.server` (`BaseHTTPRequestHandler` /
  `ThreadingHTTPServer`), which the Python docs state is not recommended for
  production. This baseline is a private lab benchmark, not a service.
- SQLite is single-instance on local disk: no NFS placement, no multi-replica
  sharing of one database file. Journal mode and SQLite version are recorded.
- No network calls, no secrets, no external fonts or CDNs in `web/` assets.

## Layout

| Path | Responsibility |
| --- | --- |
| `check.sh` | Fixed validation gate (Python compile + unittest + node checks + node tests) |
| `opsledger/__init__.py`, `__main__.py` | Package and CLI entry point |
| `opsledger/core/` | Errors, identity context, clock, IDs, database connections, migration runner |
| `opsledger/identity/` | Users, sessions, role checks, organization/site membership |
| `opsledger/assets/` | Sites, equipment, maintenance plans |
| `opsledger/workorders/` | State transitions, assignments, labor, checklists, comments |
| `opsledger/inventory/` | Parts, balances, reservations, movements, reconciliation |
| `opsledger/purchasing/` | Requests, approvals, purchase orders, receipts |
| `opsledger/incidents/` | Incidents, corrective actions, relationships to repairs |
| `opsledger/reporting/` | Authorized search, dashboards, CSV exports |
| `opsledger/audit/` | Append-only application audit and transactional outbox |
| `opsledger/http/` | Routing, bounded JSON, error mapping, cookie/CSRF handling, static allowlist |
| `opsledger/migrations/` | Append-only numbered SQL migrations with recorded checksums |
| `web/` | HTML, CSS, ES modules, no generated bundles |
| `tests/unit/`, `tests/integration/`, `tests/security/` | Python discovered tests; each directory is a regular package |
| `tests/js/` | Files named `*.test.mjs`, discovered by the fixed gate |
| `docs/` | Architecture, API contract, data dictionary, operator runbook, migration notes |
| `AGENTS.md` | Task guardrails for DevFoundry coding agents |
| `doc/` | Project spec (DevFoundry campaign document) |

Module directories beyond `opsledger/__init__.py` and `__main__.py` are listed
for orientation only; the bootstrap ships the package marker and CLI entry
point, and each module lands with its DevFoundry task.
