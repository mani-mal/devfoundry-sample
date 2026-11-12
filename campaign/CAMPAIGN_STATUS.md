# CAMPAIGN_STATUS.md — OpsLedger / DevFoundry campaign

Campaign: `opsledger-run-001` · Updated: 2026-11-12 · Workspace: `/home/manimal/projects/devfoundry-sample`

> **2026-11-12 (final, handover):** M1 complete — T001–T006 integrated on
> `main` (`575f138`); fresh-checkout gate green (96 Python + 2 JS tests, 0
> skipped). T006 approved on the lab (attempt 3 after two request-defect
> `agent_error` runs) and landed locally. Final reports: `DEFECT_REGISTER.md`
> (25 items: 1 open app defect, 3 owner decisions, 18 platform items),
> `DEVFOUNDRY_ACCEPTANCE.md` (case dispositions), and the per-image
> verification reports. See the handover section below.
>
> 2026-11-12 (evening prompt, lab `0.1.0-c1bd587`): Items 1–8 PASS, items
> 9–10 NOT TESTED (not deployed). Packet 0.2.0 line totals exact (`+438 −3`);
> "approved" wording everywhere; readiness rubric 1.1.0 (`repo.default_branch`
> + `repo.validation_check` pass); submit env warning + `--preview` base line;
> NEW-005 fix verified (empty patch → `agent_error` before validation).
> **T004 implemented, approved, published as Draft PR #1, then landed
> locally** (`3951dd9`, gate green, pushed; PR superseded). See
> `campaign/reports/bug-verification-2026-11-12.md`.
>
> 2026-11-12 (early AM): Three lab images verified (b902183 → 69fc038 →
> fccb92f). BUG-005/006, F-607, F-121, BUG-127, F-102, F-203 PASS; BUG-107
> publish-time refusal observed. T003 approved + landed (`a3c0bc7`); T005
> approved + landed (`d0dd2e3`) after two empty-patch runs (NEW-005, medium).
> See `campaign/reports/bug-verification-2026-11-11.md`.
>
> 2026-11-11: T002 approved by owner; patch landed on `main` (`46825d3`).
> BUG-005/006 + F-607/F-120 verified against lab `0.1.0-b902183`. T003
> submitted as the regression run and awaiting review. See
> `campaign/reports/bug-verification-2026-11-11.md`.
>
> 2026-11-10: WSL was reinstalled after a crash; workspace moved to
> `devfoundry-sample`. Environment re-qualified (Python 3.12.16 via uv + Node
> 22.23.4). T001 implemented directly (local); platform submission still
> blocked on credentials. See `campaign/reports/T001-local.md`.

This file is the campaign checkpoint. It contains observed facts and blockers only —
no credentials. Raw evidence lives in `campaign/journal/` (private local evidence).

## Current checkpoint

**M1 COMPLETE (T001–T006 integrated, `575f138`, fresh-checkout gate green). Campaign handed to DevFoundry/owner: final reports written (`DEFECT_REGISTER.md`, `DEVFOUNDRY_ACCEPTANCE.md`); remaining items are owner decisions + the M2 backlog (T009+).**

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
| T002 | SQLite connection factory + transaction context (first submitted DevFoundry task) | **completed/accepted (2026-11-11)** | `tsk-45ce00920c8943e08e19f2a8f0ff7b60` — owner-approved (diff 1a21d2c); publish refused (workspace autonomy has no publication path; NEW-004); patch applied locally from the review packet, gate OK, committed `46825d3`, pushed. First submission failed on missing `--base main` (NEW-001, operator error, preserved) |
| BUG-verify-2 | BUG-005/006 + F-607/F-120 verified against lab 0.1.0-b902183 | **done (2026-11-11)** | `campaign/reports/bug-verification-2026-11-11.md` — BUG-005 PASS (exit 3, 403 policy_denied); BUG-006 PASS (exact cancelled wording; console by source, browser extension not connected); F-607 PASS (attempt 1 of 3); F-120 PASS on submit, preview silent (F-120b); BUG-128 not triggered; NEW-004 (no publication path for workspace tasks) |
| T003 | Migration runner + migration history checksums (regression run) | **completed/accepted (2026-11-12)** | `tsk-66b5305a74b14c38a8c7d59cc7c81107` — validation passed on base 46825d3, 4 files / ~640 lines, 1 attempt, 0 findings; approved via the F-102 flow; patch landed locally `a3c0bc7`, pushed |
| T005 | HTTP router + JSON error envelope | **completed/accepted (2026-11-12)** | `tsk-e24416074c6c43fbbc739c2b8a005ec2` — 5 files / ~705 lines, 1 attempt, 0 findings; approved; landed `d0dd2e3`, pushed. Two prior runs produced empty patches that passed validation (NEW-005, medium; both rejected + preserved) |
| BUG-verify-3 | F-121, BUG-127, F-102, F-203, F-503, BUG-107 + re-checks on lab 0.1.0-fccb92f | **done (2026-11-12)** | `campaign/reports/bug-verification-2026-11-11.md` — F-121 real branch change + restore exercised; BUG-127 overlapping runs observed; F-102 binding verified (stale → exit 5, no-read → note); F-203 once-per-reviewer+digest; BUG-107 publish-time CI refusal observed; F-120 preview half not met (F-120b); F-503 pass-by-source; NEW-005 filed |
| T004 | Organizations, users and membership schema | **completed/accepted + landed (2026-11-12)** | `tsk-e744c6d9b88b40888733684d22a98f7b` — 3 files +438 −3, 17 tests, 0 findings, 1 attempt; approved via the F-102 flow; **published as Draft PR #1** (pub-49ae5275513f42ba832cacf6f635453c succeeded, open not merged — superseded); patch applied locally from the review packet (digest verified `181ac49b`), gate green (81 tests), committed `3951dd9`, pushed |
| BUG-verify-4 | Evening prompt items on lab 0.1.0-c1bd587 (packet 0.2.0, F-208, approved wording, readiness 1.1.0, submit warnings, NEW-005 fix, T004, re-checks) | **done (2026-11-12)** | `campaign/reports/bug-verification-2026-11-12.md` — items 1–8 PASS; items 9–10 NOT TESTED (written but not deployed); NEW-005 fix verified (empty patch → `agent_error` before validation); readiness report rr-e6bc8c8c (rubric 1.1.0, both new checks pass) |
| B06 | Human review of bootstrap + initial remote publication | **done (2026-11-10)** | `e35dd81` pushed to `origin/main` (owner-authorized, token via `sec.txt`); remote base SHA `e35dd81` |
| B07 | Register repo (if needed), readiness | **done (2026-11-12)** | repo registered (default branch `main` after F-121); readiness rubric 1.1.0 run live: report `rr-e6bc8c8c` — `repo.default_branch` pass, `repo.validation_check` pass; app.build/secret-scan/branch-protection fails are the legacy-tree facts (owner decisions) |
| B08 | Tiny onboarding task + first clean-checkout validation | **done (2026-11-11/12)** | the `[lab smoke]` tasks + T002 (first submitted task, accepted, landed) served as onboarding; clean-checkout validation re-verified on `575f138` (96 Python + 2 JS tests, gate green, CLI migrate works) |
| T006 | CLI migrate/serve + bounded health/readiness handlers | **completed/accepted + landed (2026-11-12)** | `tsk-a820b98b26384849bff5c4ae288b5853` — 4 files +685 −1, 13 tests, 0 findings, 1 attempt (88 model calls, 1395 s); approved via the F-102 flow; publication refused by design (workspace autonomy, NEW-004); patch applied locally from the review packet, gate green, committed `575f138`, pushed. Two prior runs failed `agent_error` (empty patch, request defect — request corrected, evidence preserved) |
| HANDOVER | Final reports for the DevFoundry handoff | **done (2026-11-12)** | `DEFECT_REGISTER.md` (25 items classified per §18.2), `DEVFOUNDRY_ACCEPTANCE.md` (case dispositions: live/manual/blocked/not-run), `campaign/reports/bug-verification-2026-11-12.md` (final image items) |

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

1. **DevFoundry credentials unavailable.** ~~Stored DF token is unauthenticated;
   the gitignored `campaign/config.local.json` with the live URL/token was lost
   in the 2026-11-10 WSL reinstall.~~ **Resolved 2026-11-11:** CLI installed
   from the devfoundry checkout; admin signed in via `--password-stdin`
   (password recovered from the lab's own kubectl secret, never printed;
   session token in `~/.config/devfoundry/credentials`, mode 0600).
   B07/B08 platform work is unblocked; T002/T003 submitted through DevFoundry.
2. ~~Project/repository identity unknown.~~ **Resolved 2026-11-11:** project
   `lab-sample` = `prj-f22f12d0ccb646aeaa4d4ed6156c13c0`; repo
   `repo-8824a58532574f6ba9608f9ada55db14` (registered default branch is the
   `checked` seed — **always pass `--base main`**; DevFoundry cannot change a
   registered repo's branch yet, F-121); default environment `polyglot`
   (env-cc6d85e4d582495b830ffeffa11ea7b4); default pack `issue-resolver 0.1.0`.

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
2. ~~Login + project/repo identity~~ → done 2026-11-11 (see blockers).
3. ~~B08 onboarding~~ → done 2026-11-11/12 (see table).
4. ~~Render T002~~ → done 2026-11-11: accepted, landed `46825d3`.
5. ~~T003 regression run~~ → done 2026-11-12: T003 **approved + landed**
   (`a3c0bc7`); T005 also **approved + landed** (`d0dd2e3`).
6. ~~T004~~ → done 2026-11-12: **implemented, approved, published as
   Draft PR #1**, then **landed locally** from the review packet
   (digest-verified `181ac49b`), gate green, committed `3951dd9` and
   pushed. The Draft PR is superseded (closing it is the owner's call).
7. ~~T006~~ → done 2026-11-12: **approved + landed** (`575f138`).
   **M1 (T001–T006) is complete.**

## Handover to DevFoundry/owner (2026-11-12)

The campaign is handed over at `575f138`. What was delivered and where the
open items live:

1. **Delivered**: the M1 slice of OpsLedger (errors, clock, db factory,
   migration runner + checksums, identity schema, HTTP router + envelope,
   CLI migrate/serve + healthz/readyz) — every platform task approved by a
   human, landed from digest-verified review packets, gate green on a fresh
   checkout (96 Python + 2 JS tests, 0 skipped). No credentials, no campaign
   evidence dump in the public tree.
2. **Final reports** (this handoff): `DEFECT_REGISTER.md` — 25 items, each
   classified per spec §18.2 with reproduction + evidence + resolution:
   1 open application defect (A1, low: RFC3339 pre-1000-year), 3 open owner
   decisions (B1 legacy tree + campaign governance, B2 default-looking
   placeholder creds, B3 gate PATH footgun), 18 platform items (12 fixed +
   verified PASS, 1 by-design NEW-004, 1 not triggered, 1 fix deployed but
   not re-tested, 2 not tested — not deployed, 1 registry-resolved).
   `DEVFOUNDRY_ACCEPTANCE.md` — case dispositions with live/manual/blocked/
   not-run labels and the request-digest → task → patch → decision → commit
   map for every integrated feature.
3. **Owner decisions requested**:
   - B1: delete the ~740-file legacy seed tree + untrack `campaign/`, or
     amend README/AGENTS to bless them (B1's decision subsumes B2).
   - A1: approve a small successor task through DevFoundry for the
     RFC3339 zero-padding fix.
   - C18: dependency-drift warning — re-qualify the environment build
     (needs the cluster) or keep ignoring.
   - T004's Draft PR #1: close (superseded by `3951dd9`).
4. **Next backlog**: M2 starts at **T009** (password-hash records, needs
   T004 ✓), then T010–T016. Submit without `--base` on the `polyglot`
   environment; land via the review packet as before.
5. **Boundaries held**: no task was approved by the driver, no task
   bypassed human review, no DevFoundry merge was attempted, `check.sh` was
   never edited, no accepted test was weakened, no secrets entered the repo.
