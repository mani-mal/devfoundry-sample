# CAMPAIGN_STATUS.md — OpsLedger / DevFoundry campaign

Campaign: `opsledger-run-001` · Updated: 2026-11-06 · Workspace: `/home/manimal/projects/dev-foundry-test`

This file is the campaign checkpoint. It contains observed facts and blockers only —
no credentials. Raw evidence lives in `campaign/journal/` (private local evidence).

## Current checkpoint

**B01–B05 complete locally. B06 pending (human boundary). B07/B08 + T001 blocked on credentials and base propagation.**

| ID | Work | State | Evidence |
| --- | --- | --- | --- |
| B01 | Inspect workspace, tools, credentials availability, git remotes | done (local part) | `campaign/reports/preflight-B01.md` |
| B02 | Separate campaign directory + non-secret config schema | done | `campaign/config.example.json`, contamination check below |
| B03 | Minimal package, CLI `--help`, README, AGENTS, test packages, JS baseline module/test | done | 5 Python tests + 2 JS tests pass |
| B04 | Fixed `check.sh` validation gate | done | byte-exact from spec §9.2; honest local result below |
| B05 | Driver journal schema, task template, request renderer, dry-run adapter + tests | done | 53 driver tests pass |
| B06 | Human review of bootstrap + initial remote publication | **pending** | needs owner decision (below) |
| B07 | Register repo (if needed), readiness | **pending** | needs registered base + project |
| B08 | Tiny onboarding task + first clean-checkout validation | **pending** | needs base on remote |
| T001 | Core errors + injectable UTC clock (first DevFoundry task) | **blocked** | request drafted in `campaign/requests/T001.draft.md` |

## Observed facts (B01 preflight, 2026-11-06, this laptop)

| Item | Observed | Status |
| --- | --- | --- |
| DevFoundry server health | `GET http://<devfoundry-host>:30861/healthz` → `{"status":"ok"}` | ok (live observed; real URL kept in gitignored `campaign/config.local.json`) |
| API `GET /v1/me` with stored token | `{"error":{"code":"unauthenticated",...}}` — stored token invalid/expired/revoked | **blocker: login required** |
| `devfoundry` CLI on laptop | not installed (`which devfoundry` empty) | **blocker: driver will use documented HTTP API** |
| Python (laptop) | 3.12.3 — matches qualified baseline | ok |
| Node (laptop) | 18.19.1 — qualified pod requires 22 | known limitation; gate honestly fails Node-22 step locally |
| SQLite | 3.45.1 | ok |
| git | 2.43.0 | ok |
| `gh` | installed, logged in as `mani-mal` (token redacted; protocol https) | ok — can create public GitHub repo when authorized |
| git remotes (this workspace) | none (`git remote -v` empty) | **blocker: publication path needs a remote** |
| Working tree | legacy dev-foundry build files tracked-but-deleted (` D` entries); new bootstrap files untracked | note: legacy deletions left untouched, preserved |
| Campaign scaffold | `campaign/` complete; static preflight 4 ok / 1 unknown (password_source) | ok |

Qualified environment facts are recorded per spec §12.1: laptop values are noted;
pod values (Python 3.12/pytest 8.3.5, Node 22/npm, make) come from the DevFoundry guide
§4 and must be re-confirmed at B08 via the actual task environment.

## Blockers (exact, with who can clear them)

1. **DevFoundry credentials unavailable.** Stored DF token is unauthenticated; password
   source must be operator-supplied (`--password-stdin` flow per guide §3).
   Who: owner. Needed for: B07, B08, T001.
2. **Project/repository identity unknown.** `DF_PROJECT`, `DF_REPO`, registration state,
   default environment/pack for the project unknown (no CLI/API session).
   Who: owner (`devfoundry projects`, `devfoundry repos`). Needed for: T001 submission.
3. **No git remote for this workspace.** Bootstrap (check.sh etc.) must be published to a
   public GitHub repository (e.g. `opsledger-benchmark` per spec §6.2) and registered in
   the project before any DevFoundry task — validation base must contain `check.sh`.
   Who: owner authorization required (B06 boundary — never push without it).
   `gh` is available to create the repo when authorized.
4. **Laptop Node 18** — `bash check.sh` honestly fails locally at the Node-22 check
   (all preceding Python steps pass). The qualified pod (Node 22) is the completion
   environment; local direct runs: Python suite OK, JS suite OK.

## Boundary statement (B06)

Per the spec instruction block: no push, no publication, no approval of the bootstrap
has been performed. The bootstrap awaits owner review. Required next human actions:
(1) review the new bootstrap files, (2) authorize repo creation/push + supply the
public GitHub repository name, (3) supply DF account email + password source for
`devfoundry login ... --password-stdin`, (4) name the DF project and repo to use.

## Local test results (honest, 2026-11-06)

- `python3 -m unittest discover -s tests -p "test_*.py" -t .` → Ran 5 tests, OK
- `python3 -m unittest discover -s campaign/driver/tests -p "test_*.py" -t .` → Ran 53 tests, OK
- `node --test tests/js/format.test.mjs` → tests 2, pass 2, fail 0, skipped 0
- `node --check web/js/app.mjs` → OK
- `bash check.sh` → exit 1, `Node 22 required by qualified baseline`
  (Python compile + unittest steps passed before it; expected on Node-18 laptop)
- Contamination: zero non-placeholder secret matches in new files; no campaign dirs
  outside `campaign/`; nothing committed or pushed.

## Next eligible work (once blockers clear)

1. Owner review + push bootstrap → record remote base SHA + check.sh digest (B06).
2. Login, confirm project/repo/env/pack; register repo if needed; readiness (B07).
3. Tiny onboarding task + clean-checkout validation (B08).
4. Render T001 from the verified base (draft in `campaign/requests/T001.draft.md`),
   `submit --preview`, then submit with `--mode implement --autonomy workspace
   --environment polyglot`; journal events; independent acceptance; review handoff.
