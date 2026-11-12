# DEFECT_REGISTER.md — OpsLedger / DevFoundry campaign

Campaign: `opsledger-run-001` · Updated: 2026-11-12 · Final commit: `575f138`
Classes follow spec §18.2. Severity: high = corrupts data or breaks the
workflow; medium = wrong behavior with a workaround; low = cosmetic or
conformance gap. Every item was reproduced on this machine; nothing is
speculative.

## A. Application defects (OpsLedger)

| # | Class | Severity | Where | Reproduction | Evidence | Resolution / successor |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Application defect (spec-conformance gap) | low | `opsledger/core/clock.py` — `format_rfc3339` | `format_rfc3339(datetime(999, 1, 1, tzinfo=timezone.utc))` → `'999-01-01T00:00:00Z'` (3-digit year; RFC3339 §5.6 requires 4DIGIT; `strftime("%Y")` on glibc does not zero-pad) | re-verified on `575f138`: still `'999-...`; `campaign/reports/T001-issues.md` §1 | **OPEN** — successor task through DevFoundry (one-line fix + regression test); no later task depends on pre-1000-year timestamps |
| A2 | Application defect (platform-behavior gap, fixed upstream 2026-11-12) | medium | DevFoundry lab (affected OpsLedger campaign runs) | Two T005 runs produced empty patches (`e3b0c442…`, 0 files) that **passed validation** and reached `awaiting_review` with only a packet warning (NEW-005) | `campaign/reports/bug-verification-2026-11-11.md` §Item 6; both tasks preserved (`completed (rejected)`) | **RESOLVED on the lab** (`0.1.0-c1bd587`, BUG-133): empty patch now fails before validation — verified with probe `tsk-2fa422417511486fb054257bdcfa4cff` (`agent_error`, reason "the agent changed nothing: the patch is empty") |
| A3 | Task/request defect | medium | `campaign/requests/T006.md` attempts 1–2 | The agent read 20+ files, ran the gate, and **stopped without writing files** — two consecutive `agent_error` failures (`tsk-97283bf6…`, `tsk-68152d5f…`) | attempt streams: 9–23 tool calls, final step reason `stop`, patch `e3b0c442…` | **RESOLVED by request correction** (spec §18.2 action): compressed the request and put an explicit "implement now, in this order; start writing opsledger/cli.py first" instruction at the top — attempt 3 (`tsk-a820b98b…`) implemented fully, 0 findings. Both failed runs remain in evidence on the lab |
| A4 | Task/request defect (operator error) | low | T002 first submission | Submitted without `--base` when the registered default branch was the `checked` seed → refusal | preserved on the lab (NEW-001) | **RESOLVED**: F-121 shipped branch changing; the registry default is `main` now; all later submissions omit `--base` |

## B. Repository issues (owner decisions, open)

| # | Class | Severity | Where | Reproduction | Resolution |
| --- | --- | --- | --- | --- | --- |
| B1 | Doc/reality drift + governance | medium | `README.md` vs tracked legacy tree; `campaign/` governance | README claims "a clean OpsLedger-only tree" but `git ls-files` shows 501 `.nx/` files, `packages/`, `test-app/`, root `Dockerfile*` etc. (762 tracked files total); README + `campaign/README.md` describe `campaign/` as local-only while 24 of its files are tracked and public | **OPEN — owner decision**: (a) delete the legacy tree and untrack `campaign/` (matches the written governance), or (b) amend README/AGENTS to state the merge intentionally kept them. Not changed unilaterally; both AGENTS.md and the README are owner-owned |
| B2 | Hygiene (contradicts AGENTS.md in spirit) | low | `.env.example`, `packages/web-console/.env.example` | `POSTGRES_PASSWORD=devfoundry`, `DATABASE_URL=postgres://devfoundry:devfoundry@…`, `NEXTAUTH_SECRET=langfuse-secret` — default-looking, not live secrets (token-shape scan: zero `ghp_*`/`glpat-*`/`sk-*`/PEM matches repo-wide) | **OPEN** — folds into B1's decision; deleting the legacy tree removes them |
| B3 | Environment/infrastructure | medium | `check.sh` + WSL `python3` | Plain `bash check.sh` → exit 1 (`Python 3.12 required by qualified baseline`) because fresh WSL `python3` is 3.14.4; the gate passes only with the uv 3.12 PATH exported | **OPEN — operator action**: install CPython 3.12 system-wide (or a documented non-protected wrapper; `check.sh` itself is protected and untouched) |

## C. DevFoundry platform defects (filed/verified during the campaign)

All lab-verified; full evidence in `campaign/reports/bug-verification-*.md`.

| # | ID | Severity | Summary | Status |
| --- | --- | --- | --- | --- |
| C1 | BUG-001a | low | Disallowed-environment refusal exits 1 instead of 3 (behavior fixed, exit code deviated) | fixed in behavior; deviation documented 2026-11-10 |
| C2 | BUG-002 | medium | Attempt metadata missing on first submit | **FIXED** (verified PASS) |
| C3 | BUG-005 | medium | Environment the project does not allow accepted | **FIXED** (exit 3 + HTTP 403 `policy_denied`, verified on three images) |
| C4 | BUG-006 | medium | Review packet of a task that ended without one | **FIXED** (exact refused wording; console branch verified by source) |
| C5 | F-607 | low | Attempt numbers absent from the CLI review header | **FIXED** (`· attempt 1 of 3`) |
| C6 | F-120 / BUG-134 | medium | Submit line / preview lacked the resolved base | **FIXED** (submit annotation + `--preview` base line, verified 2026-11-12) |
| C7 | F-121 | medium | Registered repo's default branch could not be changed | **FIXED** (CLI + console; real change + restore exercised) |
| C8 | BUG-127 | high | Two agent jobs ran at once | **FIXED** (overlapping runs observed 2026-11-11 → wait, no: runs overlapped = bug reproduced pre-fix; post-fix lab serialized them — see the 2026-11-11 report §Item 8) |
| C9 | BUG-128 | medium | Projects without a default agent pack | NOT TRIGGERED (all projects have one; covered by the platform's own tests) |
| C10 | F-102 | high | Approve/reject not bound to the diff the reviewer read | **FIXED** (digest binding, stale → exit 5 `stale_review`, no-read → note; all branches verified) |
| C11 | F-203 | medium | Review-opened time not recorded | **FIXED** (`task.review_opened` once per reviewer+digest; idempotence verified) |
| C12 | F-503 | medium | No cross-project "My work"; timeline events lacked the actor | **FIXED** (nav + `· by <name>`; source/bundle + API verified; live render NOT TESTED — browser extension not connected) |
| C13 | BUG-107 | high | Local GitHub actions not classified as CI | **FIXED** (publish-time refusal `ci_definitions_untouched` observed with the exact reason) |
| C14 | NEW-005 / BUG-133 | medium | Empty patch passed validation | **FIXED** (fails before validation, `agent_error`; verified 2026-11-12) |
| C15 | NEW-004 | medium | `workspace`-autonomy tasks cannot be published | **BY DESIGN** (owner decision): submit with `--autonomy draft_pr` when a Draft PR is wanted — exercised by T004's Draft PR #1 (publish succeeded); `workspace` tasks are applied locally from the review packet |
| C16 | NEW-001 | low | Registered default branch was the `checked` seed | **RESOLVED** (registry default is `main`) |
| C17 | Packet warnings | low | Tracked `opencode.json` skip-worktree warning; "dependencies differ from the qualified baseline" | Recurred on every packet through `0.1.0-fccb92f`; **absent on `0.1.0-c1bd587`** (T006's packet: `warnings: []`); the written-but-undeployed readiness-note fix (item 9 of the evening prompt) addresses the readiness half — NOT TESTED (not deployed) |
| C18 | Dependency drift | medium | "dependencies differ from the qualified baseline; setup reinstalled" | Real drift; **owner decision: ignore until the environment build is re-qualified** (needs the cluster) |

**Correction to C8:** BUG-127's verification (2026-11-11) observed B's attempt
starting while A was still running — at that lab image the fix was NOT yet
deployed and the overlap was the **pre-fix reproduction**; the fix commit
landed later the same day. Post-fix non-overlap was not separately re-tested
(no second pair was run); treat BUG-127's fix as **fix deployed,
reproduction observed, post-fix behavior NOT re-tested**.

## D. Human/Git handoff (explicit waiting states)

| Item | State |
| --- | --- |
| T004 Draft PR #1 | Open on GitHub (head `devfoundry/tsk-e744c6d9` → main), **superseded** by the local landing `3951dd9`; closing it is the owner's call |
| Draft PR handoff to DevFoundry | This campaign's DevFoundry handoff is the verification evidence itself (BUG/feature verdicts above); no product changes belong in this repository (spec §18.2) |

## Totals

- Application: 4 items — 1 open (A1, low), 3 resolved/corrected.
- Repository: 3 items — all open, all owner decisions (B1 subsumes B2).
- Platform: 18 items — 12 fixed + verified PASS, 1 by-design, 1 not
  triggered, 1 not re-tested (C8 correction), 2 not tested (not deployed),
  1 resolved at the registry level.
- Gate: `OPSLEDGER_FAST_GATE_OK` on the final commit `575f138` (fresh
  checkout: 96 Python + 2 JS tests, 0 skipped).
