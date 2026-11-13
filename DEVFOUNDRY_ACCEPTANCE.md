# DEVFOUNDRY_ACCEPTANCE.md — platform case dispositions

Campaign: `opsledger-run-001` · Updated: 2026-11-12 (late) · Lab: `0.1.0-27d7b85`
Labels per spec §19.2: **live** (observed on the lab), **fixture** (verified
by the platform's own tests), **manual** (source/bundle-verified, live
render unavailable), **blocked** (prerequisite unavailable), **not-run**.

## Core platform workflow — live observed (full sign-off basis)

| Case | Label | Evidence |
| --- | --- | --- |
| Patch/base/review integrity | **live** | Every task: submit line annotated `base main (the repository's default; --base picks another)`; review header binds the exact diff digest on the base commit (T002 `1a21d2c@3113b87`, T003 `f7728e6@46825d3`, T005 `245c71f@a7e4712`, T004 `181ac49@fc7758a`, T006 `c5cea84@9b4f589`); packets carry requirements matrices with `protected-paths-untouched` + `patch-applies` pass |
| Ordinary validation | **live** | `check:check` ran in every task's validation; receipts in the packet (`validation.check_finished`, log artifacts, `capture_complete: true`) |
| Membership isolation | **live** | Project-scoped listing: `lab-sample` tasks never leaked into other projects; `GET /v1/tasks?mine=true` returns only my tasks across my 2 role-projects |
| Dependency propagation | **live** | T003 required T002, T004 required T003, T006 required T003+T005 — each submitted only after its dependency landed; the identity schema's FK tests (T004 patch) verify cross-relationship rejection |
| Resume/retry | **live** | Session expiry mid-run (twice) → re-login and redo from the read step; no duplicate submissions (re-submissions were new tasks with preserved failed predecessors in evidence) |
| Review decision binding (F-102) | **live** | `approve` used the read digest; wrong `--diff` → exit 5 `stale_review` with "Read it again"; empty read cache → decides with the exact stderr note |
| Review-open timing (F-203) | **live** | `task.reviewed` payload has `decision: "accept"`; `task.review_opened` once per reviewer+digest, not repeated on 2nd/3rd opens (T003/T004/T005/BUG-107 task) |
| Two jobs at once (BUG-127) | **live** (pre-fix reproduction) | B's attempt started while A was still running (2026-11-11); fix deployed later that day; post-fix non-overlap NOT re-tested |

## Ordinary flow sign-off

- Submission → qualification → agent run → validation → awaiting_review →
  human approve → (optionally publish) → local landing: observed end to end
  on T002/T003/T004/T005/T006, all approved by a human (administrator
  account on the owner's authority), **no task was approved by the driver**,
  **no task bypassed human review**, **no DevFoundry merge was attempted**
  (the platform-created Draft PR #1 was left open; the local landing was a
  plain git commit + push on the owner-authorized path).
- Empty-patch guard (BUG-133): **live** — the no-op probe failed before
  validation with `agent_error`; T006's two request-defect failures failed
  the same way and never reached review.

## Conditional coverage (prerequisite-gated)

| Case group | Label | Reason |
| --- | --- | --- |
| Publication (draft PR) | **live** (partial) | T004 published as Draft PR #1: `pub-49ae5275… succeeded`, PR open/draft, head→main, scan pass; the CI-definitions refusal path also observed (BUG-107 publish failure, exact reason). Withdraw/comment/reconcile paths: **not-run** (no comment publication; reconcile correctly refused a known-outcome publication) |
| Code review (PR review flow) | **blocked** | No external PR review cycle was in scope; `code-review` commands exist but no PR review was exercised |
| CI diagnosis | **blocked** | No CI repair ran in any task (`check:check` passed first try everywhere); Diagnose-CI tasks on the lab belong to other campaigns |
| VS Code extension | **manual** | Verified headless in an earlier checkpoint (activation + 8 commands + trees, SMOKE PASS); no interactive session on this machine |
| People management (invites, roles) | **not-run** | No second human in the campaign; invitations were exercised at the API level in earlier runs only |
| Disruptive faults (pod kills, outages) | **not-run** | Not in the evening/brief prompts; lab stability was sufficient |
| Readiness (rubric 1.1.0) | **live** | Report `rr-e6bc8c8c`: `repo.default_branch` pass, `repo.validation_check` pass, environment warning on a non-assessed environment, `--preview` base line — all observed 2026-11-12; re-run after the B3 fix (`rr-f9179b98…`) and on the cleaned tree (`rr-31b16f33…`, `repo.secret_scan` pass) |
| Console rendering | **manual** | Browser MCP extension not connected on this machine; console facts verified via the served SPA bundle + frontend source (BUG-006 branch, F-503 page + timeline actor, approved wording, publish strings); live clicks NOT TESTED |
| Items 9–10 of the evening prompt (opencode.json readiness note; environment re-qualification) | **live** (9) / **live** (10) | Item 9: `repo.agent_guidance` carries the single opencode.json note (verified on `rr-f9179b98…`, `rr-31b16f33…`). Item 10: `polyglot` v4 qualifies against `main` (owner decision, C18 closed — verified on the T009 packet and both evening reports) |
| Code review agent (first live runs) | **live** | PR #3 (+23 −1): full report, conclusion `incomplete (automated check, not an approval)`, 2 real findings (OverflowError escape path; unused RFC3339_Z_FORMAT), `comment` correctly refused (started without posting). PR #2 (2.3MB deletion diff): attempt 1 `worker_lost` (979 s), attempt 2 hit the 1200 s task budget — failed, C20 |
| CI repair agent (first live runs) | **live** | Owner-authorized workflow commit `cf6d2c8` passes on `main`; probe PR #4 (deliberate `2 + 2 == 5`) failed as designed; diagnose: first unknown (`setup_failed` — stale auto-detected npm-ci app config after part 1; feedback `right` recorded), after reconfiguring the app as administrator (`kind python`, `test = bash check.sh`): `regression (high confidence)`, reproduction reproduced, comparison passes; `ci repair` proposed the exact minimal fix and the guard refused it **by design** (test-file edits refused, ruling [T9] R5); fixed by hand (one line), CI green, probe closed unmerged, branch deleted, diagnosis `done` |

## Every integrated feature maps (spec §19.2)

| Feature | Request digest → task | Patch digest | Decision | Integrated commit |
| --- | --- | --- | --- | --- |
| T001 (errors, clock) | local build (pre-platform) | n/a (local) | owner-reviewed issue list | `e35dd81` (bootstrap push) |
| T002 (db factory) | `1a21d2c…` → `tsk-45ce0092…` | `1a21d2cd…` | accept (human) | `46825d3` |
| T003 (migrations) | request `campaign/requests/T003.md` → `tsk-66b5305a…` | `f7728e66…` | accept (human) | `a3c0bc7` |
| T005 (HTTP router) | request `campaign/requests/T005.md` → `tsk-e2441607…` | `245c71fb…` | accept (human) | `d0dd2e3` |
| T004 (identity schema) | request `campaign/requests/T004.md` → `tsk-e744c6d9…` | `181ac49b…` | accept (human) | `3951dd9` (+ Draft PR #1) |
| T006 (CLI + diagnostics) | request `campaign/requests/T006.md` → `tsk-a820b98b…` | `c5cea845…` | accept (human) | `575f138` |
| Cleanup part 1 (legacy root files + B2 creds) | request `../campaign-opsledger-run-001/requests/cleanup-B1B2-part1.md` → `tsk-1b631a7c…` | `da42444b…` | accept (human) | `623bb44` + completion `a42019c` (PR #2 closed unmerged) |
| Cleanup part 2a (.nx/cache + packages) | request `requests/cleanup-B1B2-part2a.md` → `tsk-6c95b5c1…` | `13290d62…` | accept (human) | `2dd153e` |
| Cleanup part 2b (.nx/workspace-data) | request `requests/cleanup-B1B2-part2b.md` → `tsk-5dda1cea…` | `6bcb9208…` | accept (human) | `1ef2570` |
| Cleanup part 3 (test-app) | request `requests/cleanup-B1B2-part3.md` → `tsk-5f7f5e24…` | `62859138…` | accept (human) | `2a58f16` |
| A1 (RFC3339 zero-padding) | request `requests/A1-rfc3339.md` → `tsk-0ff5ac82…` | `7a0e7e47…` | accept (human) | `3131a90` (PR #3 closed unmerged) |
| T009 (password hashes) | request `requests/T009.md` → `tsk-7382eb17…` | `a5444fe0…` | accept (human) | `8afad1b` |
| T010 part A (session domain module) | request `../campaign-opsledger-run-001/requests/T010a.md` → `tsk-33b2a9cc…` | `19d64316…` | accept (human) | `f9d9e46` (merge of Draft PR #5, merged on GitHub) |
| T010 part B (sessions migration + count literals + docs) | request `../campaign-opsledger-run-001/requests/T010b.md` → `tsk-04f5553b…` | `fdb4b92d…` | accept (human) | `aea9272` (merge of Draft PR #6, merged on GitHub) |
| T011 part A (CSRF context domain module) | request `../campaign-opsledger-run-001/requests/T011a.md` → `tsk-f58d2c58…` | `3c39edf0…` | accept (human) | `321cfa5` (merge of Draft PR #7, merged on GitHub) |
| T011 part B (CSRF contexts migration + count literals + docs) | request `../campaign-opsledger-run-001/requests/T011b.md` → `tsk-ab1f9d17…` | `28d44475…` | accept (human) | `9c723bc` (merge of Draft PR #8, merged on GitHub) |
| T011 part C (user hash columns migration + integration test) | request `../campaign-opsledger-run-001/requests/T011c.md` → `tsk-2bf23823…` | `d1bcf5c3…` | accept (human) | `598203f` (merge of Draft PR #9, merged on GitHub) |
| T011 part D1 (auth service module) | request `../campaign-opsledger-run-001/requests/T011d1.md` → `tsk-af6ee3e9…` | `9814079f…` | accept (human) | `38e7453` (merge of Draft PR #10, merged on GitHub) |
| T011 part D2 (auth service integration tests) | request `../campaign-opsledger-run-001/requests/T011d2.md` → `tsk-a1c48292…` | `4655b50c…` | accept (human) | `ad8893c` (merge of Draft PR #11, merged on GitHub) |
| T012 part A (organization context module) | request `../campaign-opsledger-run-001/requests/T012a.md` → `tsk-976688c5…` | `9729fbf3…` | accept (human) | `e346dd7` (merge of Draft PR #12, merged on GitHub) |
| T012 part B (context unit + isolation tests) | request `../campaign-opsledger-run-001/requests/T012b.md` → `tsk-c5b1994c…` | `4ee331aa…` | accept (human) | `5dd3ad0` (merge of Draft PR #13, merged on GitHub) |
| T013 (role + explicit permission checks) | request `../campaign-opsledger-run-001/requests/T013.md` → `tsk-1d7f713b…` | `adabc6ae…` | accept (human) | `566c379` (merge of Draft PR #14, merged on GitHub) |
| T014 part A (site membership module + tests) | request `../campaign-opsledger-run-001/requests/T014a.md` → `tsk-9a354a46…` | `d0aab4fd…` | accept (human) | `3500b3f` (merge of Draft PR #15, merged on GitHub) |
| T014 part B (site_memberships migration + literals + docs) | request `../campaign-opsledger-run-001/requests/T014b.md` → `tsk-4b3947c7…` | `ecf93818…` | accept (human) | `e5ec1b3` (merge of Draft PR #16, merged on GitHub) |
| T015 part A (static file allowlist module) | request `../campaign-opsledger-run-001/requests/T015a.md` → `tsk-5ec77422…` | `6f4b3510…` | accept (human) | `baeb9af` (merge of Draft PR #17, merged on GitHub) |
| T015 part B (login/account UI + JS tests) | request `../campaign-opsledger-run-001/requests/T015b.md` → `tsk-c200fe27…` | `3a577dcc…` | accept (human) | `d1936e8` (merge of Draft PR #18, merged on GitHub) |
| T016 (authorization matrix regression + docs) | request `../campaign-opsledger-run-001/requests/T016.md` → `tsk-776db7f6…` | `6641e579…` | accept (human) | `e992e47` (merge of Draft PR #19, merged on GitHub) |

Intentional failures and failed successors remain in evidence: T005's two
empty-patch runs (`tsk-8626278c…`, `tsk-587b3b17…`, rejected), T006's two
request-defect runs (`tsk-97283bf6…`, `tsk-68152d5f…`, `agent_error`), the
NEW-005 probe (`tsk-2fa42241…`, `agent_error`), the BUG-107 publish
failure (`pub-f03ad672…`), the oversized single cleanup task
(`tsk-38fd16f0…`, validation_error), the two over-budget split attempts
(`tsk-5afb8a89…`, `tsk-7c2a64f9…`), the heavy code-review run
(`tsk-0d95beb3…`, worker_lost/timeout), the CI diagnose before the app
reconfig (`tsk-cab53568…`, unknown/setup_failed), and the refused CI
repair (`tsk-eceab43f…`, guard_refused by design). Nothing is hidden.
T010's four failed single-task runs remain in evidence too:
`tsk-989d2bc5…` (worker_shutdown + 1800 s timeout), `tsk-0a5f750d…`
(validation failed on four stale migration-count literals before the
allowlist was corrected), `tsk-d16982c9…` and `tsk-9d00050a…` (empty-patch
`agent_error`; one a single 32000-token output-capped response). The
T011–T016 runs keep their failures in evidence as well: T011d's
corrupted-write run (`tsk-13bf1e65…`, rejected — tests missing, write-tool
output corrupted three times) and its over-budget second run
(`tsk-679a011b…`, 1800 s timeout), and T012's single-task attempt
(`tsk-f2e6e602…`, 1800 s timeout) before the split. Nothing is hidden.
