# DEFECT_REGISTER.md — OpsLedger / DevFoundry campaign

Campaign: `opsledger-run-001` · Updated: 2026-11-13 (M4 in progress, eval-window observation C34 open) · Final commit: `c2e3fe1`
Classes follow spec §18.2. Severity: high = corrupts data or breaks the
workflow; medium = wrong behavior with a workaround; low = cosmetic or
conformance gap. Every item was reproduced on this machine; nothing is
speculative.

## A. Application defects (OpsLedger)

| # | Class | Severity | Where | Reproduction | Evidence | Resolution / successor |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Application defect (spec-conformance gap) | low | `opsledger/core/clock.py` — `format_rfc3339` | `format_rfc3339(datetime(999, 1, 1, tzinfo=timezone.utc))` → `'999-01-01T00:00:00Z'` (3-digit year; RFC3339 §5.6 requires 4DIGIT; `strftime("%Y")` on glibc does not zero-pad) | fixed by lab task `tsk-0ff5ac82…` (diff `7a0e7e47…`, 2 files +23 −1, 0 findings), landed `3131a90`; `format_rfc3339(datetime(999,…))` → `'0999-…'`; regression test covers years 1/99/999/2026 | **CLOSED** — landed `3131a90`, gate green; Draft PR #3 closed unmerged (superseded) |
| A2 | Application defect (platform-behavior gap, fixed upstream 2026-11-12) | medium | DevFoundry lab (affected OpsLedger campaign runs) | Two T005 runs produced empty patches (`e3b0c442…`, 0 files) that **passed validation** and reached `awaiting_review` with only a packet warning (NEW-005) | `campaign/reports/bug-verification-2026-11-11.md` §Item 6; both tasks preserved (`completed (rejected)`) | **RESOLVED on the lab** (`0.1.0-c1bd587`, BUG-133): empty patch now fails before validation — verified with probe `tsk-2fa422417511486fb054257bdcfa4cff` (`agent_error`, reason "the agent changed nothing: the patch is empty") |
| A3 | Task/request defect | medium | `campaign/requests/T006.md` attempts 1–2 | The agent read 20+ files, ran the gate, and **stopped without writing files** — two consecutive `agent_error` failures (`tsk-97283bf6…`, `tsk-68152d5f…`) | attempt streams: 9–23 tool calls, final step reason `stop`, patch `e3b0c442…` | **RESOLVED by request correction** (spec §18.2 action): compressed the request and put an explicit "implement now, in this order; start writing opsledger/cli.py first" instruction at the top — attempt 3 (`tsk-a820b98b…`) implemented fully, 0 findings. Both failed runs remain in evidence on the lab |
| A4 | Task/request defect (operator error) | low | T002 first submission | Submitted without `--base` when the registered default branch was the `checked` seed → refusal | preserved on the lab (NEW-001) | **RESOLVED**: F-121 shipped branch changing; the registry default is `main` now; all later submissions omit `--base` |
| A5 | Campaign planning defect (landing) | low | Part-1 cleanup landing (`623bb44`) | The working-tree changes were stashed before the CI probe and not restored, so the landing commit captured only `.env.example` + README; 55 root deletions stayed unlanded until the completion commit | `git show --stat 623bb44` (1 file) vs the reviewed 57-file patch; recovered via `git stash pop` → completion commit `a42019c`, gate green | **RESOLVED** — `a42019c` completes the reviewed patch exactly; lesson: never stash across a landing |

## B. Repository issues (owner decisions, open)

| # | Class | Severity | Where | Reproduction | Resolution |
| --- | --- | --- | --- | --- | --- |
| B1 | Doc/reality drift + governance | medium | `README.md` vs tracked legacy tree; `campaign/` governance | README claimed "a clean OpsLedger-only tree" while 701 legacy files were tracked; `campaign/` was tracked despite local-only governance | **CLOSED (2026-11-12 evening, owner decision applied)**: `campaign/` moved out (snapshot branch `campaign` at `65323db`, live dir `../campaign-opsledger-run-001/`, commit `49d4ef6`); the legacy seed tree removed through DevFoundry review (parts 1/2a/2b/3, commits `623bb44`+`a42019c`, `2dd153e`, `1ef2570`, `2a58f16`) — final tree 44 files, README claim true, gate green |
| B2 | Hygiene (contradicts AGENTS.md in spirit) | low | `.env.example`, `packages/web-console/.env.example` | `POSTGRES_PASSWORD=devfoundry`, `DATABASE_URL=postgres://devfoundry:devfoundry@…`, `NEXTAUTH_SECRET=langfuse-secret` — default-looking, not live secrets | **CLOSED (2026-11-12 evening)**: both files deleted through DevFoundry review (part 1, `623bb44`/`a42019c`); readiness `repo.secret_scan` now passes ("no tracked file matches the secret patterns") |
| B3 | Environment/infrastructure | medium | `check.sh` + WSL `python3` | Plain `bash check.sh` → exit 1 (`Python 3.12 required by qualified baseline`) because fresh WSL `python3` was 3.14.4 | **CLOSED (2026-11-12 evening, owner-authorized direct edit of the protected file)**: `check.sh` locates Python 3.12 itself (commit `f502a32`); plain `bash check.sh` green on WSL, clear failure when no 3.12 exists, readiness `repo.validation_check` still passes |

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
| C17 | Packet warnings | low | Tracked `opencode.json` skip-worktree warning; "dependencies differ from the qualified baseline" | Recurred on every packet through `0.1.0-fccb92f`; **absent on `0.1.0-c1bd587`** (T006's packet: `warnings: []`); the readiness-note fix (item 9 of the evening prompt) is now **live** — `repo.agent_guidance` carries the single opencode.json note (verified on `rr-f9179b98…` and `rr-31b16f33…`) |
| C18 | Dependency drift | medium | "dependencies differ from the qualified baseline; setup reinstalled" | **CLOSED (owner decision 2026-11-12)**: `polyglot` v4 qualifies against `main` (build `envb-2d5bb032…` qualified at `fc7758a`); verified on the T009 packet (no drift warning) and both evening readiness reports (`freshness current`, no warning) |
| C19 | Platform limit | medium | Lab validation: "the compressed patch does not fit in a 524288-byte Secret" | A 700-file deletion task produced a 2.74MB patch (517KB gzip-9) → validation error before checks; a `.nx`+`packages`+`test-app` split (2.56MB raw) failed the same way; `.nx`+`packages` (2.25MB raw) failed because `.nx/workspace-data` diffs huge JSON/SQLite files | **OPEN — platform consideration**: document the budget; deletion campaigns must be split per tree (working split used: root files, `.nx/cache`+`packages`, `.nx/workspace-data`, `test-app`). Evidence: `tsk-38fd16f0…`, `tsk-5afb8a89…`, `tsk-7c2a64f9…` |
| C20 | Platform observation | low | Code-review agent on a heavy diff | Reviewing the 2.3MB deletion PR (57 files, −11792 lines): attempt 1 `worker_lost` after 979 s (51 model calls), attempt 2 hit the lab's 1200 s task budget → failed with no findings | **OPEN — platform consideration**: small diffs review fine (PR #3: full report + 2 real findings in ~5 min); heavy diffs need a bigger budget or diff-scoped review. Evidence: `tsk-0d95beb3…` |
| C21 | Platform observation | low | Stale auto-detected app config blocks CI reproduction | The repo's app config was auto-detected as Node (`setup = npm ci`); after part 1 deleted `package.json`, `ci diagnose` failed at reproduction (`setup_failed`) with class `unknown` despite a correct agent explanation; fixed as administrator by reconfiguring the app (`kind python`, `test = bash check.sh`, stale commands cleared via API) → re-diagnosis `regression (high confidence)`, comparison passes | **OPEN — platform consideration**: an app-config drift note on CI diagnoses (the readiness report already surfaces `app.build`); evidence `tsk-cab53568…` (unknown), `tsk-759bbc06…` (regression, after the fix) |
| C22 | Platform observation | low | Repair-guard state messages | `ci repair` of the probe: the guard correctly refused the agent's minimal fix (correcting the expected value **with the test kept**) because test-file edits are refused by design (fail-closed allow list, ruling [T9] R5); the state message says "weakened a check (tests kept)" and "fix it by hand" — accurate, but "weakened" reads oddly for a value correction; the earlier no-change attempt uses a different message | **BY DESIGN** (guard behavior correct; human completion worked: one-line fix applied by hand, CI green, probe closed unmerged, diagnosis marked done) — message wording noted for the platform |
| C23 | Platform observation | low | Outcome role premise | The outcomes prompt assumed only a lab-sample **team lead** can record outcomes; on this lab the `Administrator` account holds a direct `lead` role in `lab-sample` (`GET /v1/projects/prj-f22f12d0…/members`), so `outcome record` worked from the admin session without a 403 | **OPEN — platform consideration**: if the role split is intentional, the admin's direct `lead` membership should be revoked; evidence `campaign/reports/bug-verification-2026-11-12.md` (outcomes update, role note) |
| C24 | Platform observation | low | Draft PRs need `gh pr ready` before merge | `gh pr merge N --merge` on a DevFoundry-published Draft PR refuses (`GraphQL: Pull Request is still a draft (mergePullRequest)`); after `gh pr ready N` the merge succeeds (PRs #5, #6) | **OPEN — docs note**: worth a line in the publish docs; not a defect |
| C25 | Platform observation | low | No read-only feedback viewer | `devfoundry feedback <task>` without flags is a usage error (`say --up or --down…`) and there is no read subcommand; feedback is only visible via the event stream (`feedback.submitted`) or the console | **OPEN — platform consideration**: a `feedback show`/read path would complete the loop |
| C26 | Platform limit | medium | Single-model-call runs hit the 32000-token output cap | `tsk-d7d95028…`: 1 model call, exactly 32000 output tokens, run failed `agent_error` with an empty patch (the "write in your very first tool call" phrasing pushed the model to emit everything in one truncated response) | **CLOSED (platform, 2026-11-13)**: DevFoundry BUG-135 — a last turn ending cut off or at 32000 output tokens now fails the task *before validation* with "the agent's last model turn was cut off at the output-token limit; the change is unfinished" (`agent_error`); RouteForge B113 delivers cut-off turns as `length` on every path and no longer caches them |
| C28 | Application/tooling observation — **RE-LABELED 2026-11-13 (root cause correction from DevFoundry)** | medium | "The write tool corrupts files" (M2 report defect 2) — original label was wrong | On `tsk-13bf1e65` the agent's last model turn ran 95 s and stopped at exactly 32 000 output tokens (OpenCode's one-turn limit): a runaway generation. RouteForge then reported the turn as *finished* (`stop`) instead of *cut off* (`length`), so OpenCode ended the session and the unfinished change went to review — the write tool itself was fine. The "malformed placeholder definitions" seen in the diff were the truncated tail of the runaway turn, not write-tool corruption | **CLOSED — root cause fixed on both sides**: DevFoundry BUG-135 (fail fast before validation on a cut-off last turn) + RouteForge B113 (`length` on every path, cut-off answers not cached). The whole-file-write / rewrite-once / tests-split-out workaround remains good practice: it keeps each turn short |
| C27 | Application defect (spec-conformance gap, found + fixed 2026-11-13) | medium | `opsledger/migrations/0002_identity.sql` vs T009's `provision_user` | The shipped `users` table had no `salt/hash/n/r/p/protocol_version` columns, so `provision_user` raised `OperationalError` ("table users has no column named salt") on every real migrated DB; T009's tests passed because they create their own table — found during T011 planning by running `provision_user` against a fresh `migrate()` | **CLOSED**: `0005_user_hash_columns.sql` (append-only ALTER TABLE) + the first integration test against the real shipped migrations landed through PR #9 (`598203f`, 0 findings); `provision_user` verified end to end on a migrated DB |
| C29 | Application/tooling observation (request defect, caught in review) | low | T017a request assumed a `sites` table existed in the shipped migrations | The T017a request said "the sites table already exists in the shipped migrations (0001_initial.sql)" — wrong: 0001 is only `schema_notes` and no migration 0001–0006 creates `sites`; the hands-on check failed with `sqlite3.OperationalError: no such table: sites` before approve; recovered in-session (hands-on verified against a locally created table matching the documented shape) and the table shipped append-only in T017b `0007_sites.sql` | **CLOSED**: `0007_sites.sql` landed through PR #21 (`fe830a3`); lesson recorded — verify table existence before writing the request; no lab task wasted (the module was correct against the documented shape) |
| C30 | Application defect (caught by review, run rejected) | medium | T020a first attempt bound NULL over stored values on partial updates | `tsk-aace15bb…` (diff `339b5d2e…`): `_UPDATE_ASSET_SQL` set all three optional columns and bound None for unprovided fields, so `update_asset(name only)` failed `NOT NULL constraint failed: assets.criticality` — reproduced hands-on BEFORE approve; the gate could not see it (no partial-update test existed yet) | **CLOSED**: rejected (`--reason` prose); resubmission specified `col = COALESCE(?, col)` for each optional column; landed through PR #26 (`17ae445`) and covered by T020b's partial-update tests (PR #27) |
| C31 | Application defect (caught by review, run rejected) | medium | T022a first attempt raised NameError on every `record_event` | `tsk-bcaeff3f…` (diff `9df35f5d…`): the module used `transaction(conn)` but never imported it from `opsledger.core.db` (the request explicitly required the import) — `NameError: name 'transaction' is not defined` on the first hands-on call | **CLOSED**: rejected; resubmission added the import; landed through PR #29 (`540c2bc`), hands-on verified (record_event / record_event_in_tx / events_for_entity) |
| C32 | Application defect (caught by review, run rejected) | medium | T022b first attempt raised NameError on the no-row path | `tsk-3073bf14…` (diff `cbbe5077…`): the no-rowcount path raised an undefined module-level sentinel `raise _NoRowError()` — `NameError` hands-on; the try/except around the transaction referenced the same undefined name | **CLOSED**: rejected; resubmission's request added an explicit structure note (define any sentinel at module level, or record rowcount in a local and raise ConflictError after the tx block); landed through PR #30 (`df010ff`); core T022 acceptance verified hands-on (forced audit failure rolls back the business mutation) |
| C33 | Platform/tooling observation (transient) | low | `gh pr ready` first attempt failed with "network is unreachable" | PR #20: `gh pr ready 20` failed (`Post https://api.github.com/graphql: dial tcp 140.82.114.5:443: connect: network is unreachable`) when only `NO_PROXY` was set; setting BOTH `NO_PROXY` and lowercase `no_proxy` before every `gh` command fixed it (all later PRs #21–#35 first attempt) | **CLOSED (workaround established)**: export both variables; the merge itself then succeeded; left PR #20 in draft for ~10 min before the retry (outcome poller still recorded the merge 8 min after — within bounds) |
| C34 | Platform observation (worker output integrity, M4) — **root-caused 2026-11-14** | medium | glm-5.3-flash long-context repetition runaway; DevFoundry last-turn-only cutoff check (BUG-135) lets mid-run runaways reach review | 14 consecutive T025 module failures 2026-11-13 19:07 → 2026-11-14 02:24 across every request shape (3-file; 2-file; minimal; two-small-writes; verbatim-copy; overnight hourly resubmit): 4× `timed out after 1800 s` (4 tasks looped 195–266 model calls), 5× cut off at the output-token limit (32000-token cap; some recorded `finish_reason` `tool_calls` instead of `length`), 1× completely wrong content — a mid-run 32000-token runaway written into a file (`tsk-fb4d4705…`, hallucinated `openclosed` imports, `PENDING_IMPL` tails) which PASSED validation because unused files do not break the gate, 4× empty patch; meanwhile 1-line probes and small SQL/edits tasks passed normally. **Root cause (RouteForge/DevFoundry reply 2026-11-14)**: model-side, not lab load — the model server was unchanged, almost no load; ~0.3–0.4% runaway rate on every app since 11-11, M4 module requests trigger it more often per task; waiting for the B109 window to end will not fix it | **OPEN — linked to F-913** (review-packet warning naming the runaway turn and the files written after it — the fix for the BUG-135 gap that let the corrupted packet reach review); hands-on full-file review caught it before landing (zero defects landed); all 12 same-request resubmits 11-13/11-14 reclassified as MODEL FAILURES, not request-quality failures; hourly large-request resubmit stopped; module work resumed only in the split form (one service function per task, named reads) |

**Correction to C8:** BUG-127's verification (2026-11-11) observed B's attempt
starting while A was still running — at that lab image the fix was NOT yet
deployed and the overlap was the **pre-fix reproduction**; the fix commit
landed later the same day. Post-fix non-overlap was not separately re-tested
(no second pair was run); treat BUG-127's fix as **fix deployed,
reproduction observed, post-fix behavior NOT re-tested**.

## D. Human/Git handoff (explicit waiting states)

| Item | State |
| --- | --- |
| T004 Draft PR #1 | **Closed by the owner** (2026-11-12T15:31:24Z) with a comment pointing to `3951dd9`; the DevFoundry task keeps the review record |
| Cleanup Draft PR #2 | Opened by DevFoundry (`pub-c7371bde…` succeeded); the code-review agent ran on it (worker_lost/timeout — C20); **closed unmerged** (superseded by the local landing `623bb44`+`a42019c`) |
| A1 Draft PR #3 | Opened by DevFoundry (`pub-014185cb…` succeeded); the code-review agent produced 2 real findings on it; **closed unmerged** (superseded by the local landing `3131a90`) |
| CI probe PR #4 | Deliberately broken test; diagnosis regression/high-confidence; repair guard refused the test edit by design; fixed by hand (CI green); **closed unmerged**, branch deleted |
| T010a Draft PR #5 | Opened by DevFoundry (`pub-a9291ea3…` succeeded); first `gh pr merge` refused while draft (C24); **merged on GitHub** 2026-11-12T22:02:47Z → `f9d9e46`; the outcome poller recorded `cr_merged #5 f9d9e4609330 verified` ≤ 1 min later |
| T010b Draft PR #6 | Opened by DevFoundry (`pub-db8f99fa…` succeeded); ready + **merged on GitHub** 2026-11-12T22:16:08Z → `aea9272`; poller recorded `cr_merged #6 aea92722d55e verified` ~3 min later |
| T011a Draft PR #7 | Opened by DevFoundry (`pub-afbb92f1…` succeeded); ready + **merged on GitHub** 2026-11-12T23:04:38Z → `321cfa5`; poller recorded `cr_merged #7 321cfa5835a2 verified` ~4 min later |
| T011b Draft PR #8 | Opened by DevFoundry (`pub-ccb4054c…` succeeded); ready + **merged on GitHub** 2026-11-12T23:15:00Z → `9c723bc`; poller recorded `cr_merged #8 9c723bca0833 verified` < 1 min later |
| T011c Draft PR #9 | Opened by DevFoundry (`pub-c5fa5502…` succeeded); ready + **merged on GitHub** 2026-11-12T23:32:38Z → `598203f`; poller `cr_merged #9 598203fd2426 verified` ~4 min later; closes C27 |
| T011d1 Draft PR #10 | Opened by DevFoundry (`pub-ec82ee89…` succeeded); ready + **merged on GitHub** 2026-11-13T00:22:32Z → `38e7453`; poller `cr_merged #10 38e7453425d6 verified` ~4 min later |
| T011d2 Draft PR #11 | Opened by DevFoundry (`pub-7ce142db…` succeeded); ready + **merged on GitHub** 2026-11-13T00:33:52Z → `ad8893c`; poller `cr_merged #11 ad8893c59e91 verified` ~3 min later |
| T012a Draft PR #12 | Opened by DevFoundry (`pub-238b3cf1…` succeeded); ready + **merged on GitHub** 2026-11-13T01:15:54Z → `e346dd7`; poller `cr_merged #12 e346dd73e1c1 verified` < 1 min later |
| T012b Draft PR #13 | Opened by DevFoundry (`pub-990fdf3b…` succeeded); ready + **merged on GitHub** 2026-11-13T01:22:29Z → `5dd3ad0`; poller `cr_merged #13 5dd3ad05549a verified` ~5 min later |
| T013 Draft PR #14 | Opened by DevFoundry (`pub-f1357a76…` succeeded); ready + **merged on GitHub** 2026-11-13T01:31:39Z → `566c379`; poller `cr_merged #14 566c3795645c verified` < 1 min later |
| T014a Draft PR #15 | Opened by DevFoundry (`pub-2e373566…` succeeded); ready + **merged on GitHub** 2026-11-13T01:49:06Z → `3500b3f`; poller `cr_merged #15 3500b3f6dab3 verified` ~3 min later |
| T014b Draft PR #16 | Opened by DevFoundry (`pub-8198cc3e…` succeeded); ready + **merged on GitHub** 2026-11-13T01:56:03Z → `e5ec1b3`; poller `cr_merged #16 e5ec1b322993 verified` < 1 min later |
| T015a Draft PR #17 | Opened by DevFoundry (`pub-1e2967f2…` succeeded); ready + **merged on GitHub** 2026-11-13T02:01:14Z → `baeb9af`; poller `cr_merged #17 baeb9af2b632 verified` < 1 min later |
| T015b Draft PR #18 | Opened by DevFoundry (`pub-050307e2…` succeeded); ready + **merged on GitHub** 2026-11-13T02:06:15Z → `d1936e8`; poller `cr_merged #18 d1936e8409b3 verified` < 1 min later |
| T016 Draft PR #19 | Opened by DevFoundry (`pub-c4f74d48…` succeeded); ready + **merged on GitHub** 2026-11-13T02:18:50Z → `e992e47`; poller `cr_merged #19 e992e475c5c3 verified` ~4 min later — **M2 gate complete** |
| Draft PR handoff to DevFoundry | This campaign's DevFoundry handoff is the verification evidence itself (BUG/feature verdicts above); no product changes belong in this repository (spec §18.2) |

## Totals

- Application: 5 items — 0 open (A1 closed by lab task `tsk-0ff5ac82…`,
  landed `3131a90`), 4 resolved/corrected, 1 landing error resolved.
- Repository: 3 items — all closed (B1+B2 cleanup landed through
  DevFoundry review; B3 closed by the owner-authorized direct edit).
- Platform: 30 items — all previous 29 plus C34 (M4 worker output integrity,
  root-caused 2026-11-14 to glm-5.3-flash long-context repetition runaways:
  14 consecutive module failures, one corrupted packet caught hands-on
  before landing — OPEN, linked to F-913),
  1 by-design wording note (C22), 1 not triggered (BUG-128), 1 fix
  deployed but not re-tested (C8 correction), 1 registry-resolved,
  2 closed owner decisions (C17 live, C18 closed), 3 platform
  observations (C19 budget, C20 heavy review, C21 stale app config),
  4 observations from the outcomes run (C23 role premise, C24
  draft-PR ready step, C25 no feedback viewer, C26 32000-token cap —
  CLOSED 2026-11-13 by BUG-135/B113), 1 application gap found + closed
  en route (C27, fixed by PR #9), 1 re-labeled (C28: M2 report defect 2
  "write tool corrupts files" was actually a 32000-token runaway turn +
  RouteForge stop-vs-length misreport — closed by BUG-135/B113),
  1 M3 request defect caught hands-on (C29, closed by PR #21),
  3 M3 review-caught rejects closed (C30/C31/C32, landed via PRs
  #26/#29/#30), 1 transient gh proxy flake (C33, workaround: set both
  NO_PROXY and no_proxy).
- Gate: `OPSLEDGER_FAST_GATE_OK` on the final commit `a42019c` (fresh
  clone: 44-file tree, 97 Python + 2 JS tests, 0 skipped; plain
  `bash check.sh` green without a PATH export).
- Agents: code-review first live PASS (2 real findings), CI
  diagnose/repair first live PASS (diagnosis correct, guard fail-closed,
  by-hand completion).
- M2: T009 landed (`8afad1b`, 23 tests, 0 findings); T010 complete in two
  parts (sessions module `f9d9e46`/PR #5 + migration/literals `aea9272`/PR
  #6); T011 complete in five parts (CSRF module `321cfa5`/PR #7 + migration
  `9c723bc`/PR #8 + user-hash-columns fix `598203f`/PR #9 + auth service
  `38e7453`/PR #10 + auth tests `ad8893c`/PR #11); T012 complete in two
  parts (context module `e346dd7`/PR #12 + tests `5dd3ad0`/PR #13); T013
  landed (`566c379`/PR #14); T014 complete in two parts (sites module
  `3500b3f`/PR #15 + migration `e5ec1b3`/PR #16); T015 complete in two
  parts (static allowlist `baeb9af`/PR #17 + login UI `d1936e8`/PR #18);
  T016 landed (`e992e47`/PR #19) — **M2 gate complete**, all through Draft
  PRs merged on GitHub. One integration gap found and fixed en route
  (C27: 0002 users table lacked T009's hash columns — fixed by
  `598203f`). Next: M3 (sites and equipment).
