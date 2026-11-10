# CAMPAIGN_STATUS.md — OpsLedger / DevFoundry campaign

Campaign: `opsledger-run-001` · Updated: 2026-11-10 · Workspace: `/home/manimal/projects/devfoundry-sample`

> 2026-11-10: WSL was reinstalled after a crash; workspace moved to
> `devfoundry-sample`. Environment re-qualified (Python 3.12.16 via uv + Node
> 22.23.4). T001 implemented directly (local); platform submission still
> blocked on credentials. See `campaign/reports/T001-local.md`.

This file is the campaign checkpoint. It contains observed facts and blockers only —
no credentials. Raw evidence lives in `campaign/journal/` (private local evidence).

## Current checkpoint

**B01–B05 complete locally. T001 implemented locally (gate green). B06 pending (human boundary). B07/B08 platform submission blocked on credentials.**

| ID | Work | State | Evidence |
| --- | --- | --- | --- |
| B01 | Inspect workspace, tools, credentials availability, git remotes | done (local part) | `campaign/reports/preflight-B01.md` |
| B02 | Separate campaign directory + non-secret config schema | done | `campaign/config.example.json`, contamination check below |
| B03 | Minimal package, CLI `--help`, README, AGENTS, test packages, JS baseline module/test | done | 5 Python tests + 2 JS tests pass |
| B04 | Fixed `check.sh` validation gate | done | byte-exact from spec §9.2; honest local result below |
| B05 | Driver journal schema, task template, request renderer, dry-run adapter + tests | done | 53 driver tests pass |
| T001 | Core errors + injectable UTC clock | **done (local, 2026-11-10)** | `campaign/reports/T001-local.md`; gate exit 0 (32 Python + 2 JS tests) |
| T001-review | Post-build issue list | **done (2026-11-10)** | `campaign/reports/T001-issues.md` — 1 code defect (pre-1000-year RFC3339), 4 repo/env issues, B07/B08 platform blockers unchanged |
| T001-triage | Issues classified per spec §18.2; DevFoundry bug report drafted | **done (2026-11-10)** | `campaign/reports/T001-devfoundry-bug-report.md` — A: 5 repo items, B: task layer, C: 3 candidate DevFoundry platform issues (C1 env/toolchain guard = medium) |
| BUG-verify | BUG-001..004 verified against lab after CLI reinstall from fix branch | **done (2026-11-10)** | `campaign/reports/bug-verification-2026-11-10.md` — BUG-002 fully fixed; BUG-001 fixed in behavior (exit 1 vs 3 deviation filed as BUG-001a); attempt metadata confirmed (1 per implement task); 3 new papercuts filed |
| T002 | SQLite connection factory + transaction context (first submitted DevFoundry task) | **awaiting_review (2026-11-10)** | `tsk-45ce00920c8943e08e19f2a8f0ff7b60` — validation passed on base 3113b87, 4 files / 359 lines, 1 attempt, protected paths untouched; first submission failed on missing `--base main` (NEW-001, operator error, preserved) |
| B06 | Human review of bootstrap + initial remote publication | **done (2026-11-10)** | `e35dd81` pushed to `origin/main` (owner-authorized, token via `sec.txt`); remote base SHA `e35dd81` |
| B07 | Register repo (if needed), readiness | **pending** | needs DF credentials (lost in WSL reinstall) |
| B08 | Tiny onboarding task + first clean-checkout validation | **pending** | needs DF credentials + registered base |

## Observed facts (B01 preflight, 2026-11-06; re-verified 2026-11-10 after WSL reinstall)

| Item | Observed | Status |
| --- | --- | --- |
| DevFoundry server health | `GET http://<devfoundry-host>:30861/healthz` → `{"status":"ok"}` | ok (live observed 2026-11-06; `campaign/config.local.json` lost in WSL reinstall — recreate from `campaign/config.example.json`) |
| API `GET /v1/me` with stored token | `{"error":{"code":"unauthenticated",...}}` — stored token invalid/expired/revoked | **blocker: login required** |
| `devfoundry` CLI on laptop | not installed (`which devfoundry` empty) | **blocker: driver will use documented HTTP API** |
| Python (laptop, 2026-11-10) | 3.14.4 system; **3.12.16 via uv** (`~/.local/share/uv/python/cpython-3.12.16-linux-x86_64-gnu/bin`) — gate needs the uv 3.12 on PATH | ok with uv 3.12 |
| Node (laptop, 2026-11-10) | 22.23.4 (was 18 before the reinstall) | ok — full gate now runs locally |
| SQLite | 3.46.1 | ok |
| git | 2.43.0 | ok |
| `gh` | installed, logged in as `mani-mal` (token redacted; protocol https) | ok — can create public GitHub repo when authorized |
| git remotes (this workspace, 2026-11-10) | `origin` → `https://github.com/mani-mal/devfoundry-sample.git`, branch pushed through 936d69d | **old blocker cleared**; T001 commit awaits owner push |
| Working tree | clean before T001; legacy seed files (packages/, Dockerfile*, docs/tech, test-app/) still tracked | note: public history per owner-instructed merge commit 936d69d |
| Campaign scaffold | `campaign/` complete; journal re-initialized after crash (empty, append-only) | ok |

Qualified environment facts are recorded per spec §12.1: laptop values are noted;
pod values (Python 3.12/pytest 8.3.5, Node 22/npm, make) come from the DevFoundry guide
§4 and must be re-confirmed at B08 via the actual task environment.

## Blockers (exact, with who can clear them)

1. **DevFoundry credentials unavailable.** Stored DF token is unauthenticated;
   the gitignored `campaign/config.local.json` with the live URL/token was lost
   in the 2026-11-10 WSL reinstall. Password source must be operator-supplied
   (`--password-stdin` flow per guide §3).
   Who: owner. Needed for: B07, B08 (platform submission of T001 and later tasks).
2. **Project/repository identity unknown.** `DF_PROJECT`, `DF_REPO`, registration state,
   default environment/pack for the project unknown (no CLI/API session).
   Who: owner (`devfoundry projects`, `devfoundry repos`). Needed for: T001 platform submission.

## Boundary statement (B06)

B06 is now **complete** (2026-11-10): the owner authorized publication using the
git credential from `/home/manimal/sec.txt`; commit `e35dd81` was pushed to
`origin/main` (fast-forward from `936d69d`, no merge conflicts — local was
strictly ahead). The push used a temporary in-process credential helper so the
token never landed in argv, shell history, or this repository.

Remaining human actions (platform only): (1) supply DF account email + password
source for `devfoundry login ... --password-stdin` (`campaign/config.local.json`
was lost in the WSL reinstall), (2) name the DF project and repo to use.

## Local test results (honest, 2026-11-10, after WSL reinstall)

Qualified environment: Python 3.12.16 (uv) + Node 22.23.4.

- `bash check.sh` → exit 0, `OPSLEDGER_FAST_GATE_OK` — first fully green local
  gate (Node 22 now available; before the reinstall the laptop had Node 18)
- Python: Ran 32 tests, OK (7 bootstrap + 14 errors + 13 clock)
- `python3.12 -m unittest tests.unit.test_core_errors tests.unit.test_clock -v` → Ran 27 tests, OK
- `python3.12 -m unittest discover -s campaign/driver/tests -p "test_*.py" -t .` → Ran 53 tests, OK
- `node --test tests/js/format.test.mjs` → tests 2, pass 2, fail 0, skipped 0
- `node --check web/js/app.mjs` → OK
- Contamination: zero non-placeholder secret matches in new files; no campaign
  dirs outside `campaign/`; journal re-initialized after crash; nothing pushed.

## Next eligible work (once blockers clear)

1. ~~Owner review + push T001 commit~~ → done 2026-11-10: `e35dd81` on `origin/main`, remote base SHA recorded (B06 complete).
2. Recreate `campaign/config.local.json`, login, confirm project/repo/env/pack;
   register repo if needed; readiness (B07).
3. Tiny onboarding task + clean-checkout validation (B08).
4. Render T002 (SQLite connection factory + transaction context) from the
   implemented clock/error API per spec §11 (`render T002 against the
   implemented clock/error API rather than guessing its interface in advance`),
   `submit --preview`, then submit with `--mode implement --autonomy workspace
   --environment polyglot`; journal events; independent acceptance; review handoff.
