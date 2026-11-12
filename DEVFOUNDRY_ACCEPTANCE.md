# DEVFOUNDRY_ACCEPTANCE.md — platform case dispositions

Campaign: `opsledger-run-001` · Updated: 2026-11-12 · Lab: `0.1.0-c1bd587`
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
