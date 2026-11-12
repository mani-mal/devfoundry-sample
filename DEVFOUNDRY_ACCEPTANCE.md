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
| Readiness (rubric 1.1.0) | **live** | Report `rr-e6bc8c8c`: `repo.default_branch` pass, `repo.validation_check` pass, environment warning on a non-assessed environment, `--preview` base line — all observed 2026-11-12 |
| Console rendering | **manual** | Browser MCP extension not connected on this machine; console facts verified via the served SPA bundle + frontend source (BUG-006 branch, F-503 page + timeline actor, approved wording, publish strings); live clicks NOT TESTED |
| Items 9–10 of the evening prompt (opencode.json readiness note; environment re-qualification) | **blocked** | Written but not deployed; the lab still runs `0.1.0-c1bd587` |

## Every integrated feature maps (spec §19.2)

| Feature | Request digest → task | Patch digest | Decision | Integrated commit |
| --- | --- | --- | --- | --- |
| T001 (errors, clock) | local build (pre-platform) | n/a (local) | owner-reviewed issue list | `e35dd81` (bootstrap push) |
| T002 (db factory) | `1a21d2c…` → `tsk-45ce0092…` | `1a21d2cd…` | accept (human) | `46825d3` |
| T003 (migrations) | request `campaign/requests/T003.md` → `tsk-66b5305a…` | `f7728e66…` | accept (human) | `a3c0bc7` |
| T005 (HTTP router) | request `campaign/requests/T005.md` → `tsk-e2441607…` | `245c71fb…` | accept (human) | `d0dd2e3` |
| T004 (identity schema) | request `campaign/requests/T004.md` → `tsk-e744c6d9…` | `181ac49b…` | accept (human) | `3951dd9` (+ Draft PR #1) |
| T006 (CLI + diagnostics) | request `campaign/requests/T006.md` → `tsk-a820b98b…` | `c5cea845…` | accept (human) | `575f138` |

Intentional failures and failed successors remain in evidence: T005's two
empty-patch runs (`tsk-8626278c…`, `tsk-587b3b17…`, rejected), T006's two
request-defect runs (`tsk-97283bf6…`, `tsk-68152d5f…`, `agent_error`), the
NEW-005 probe (`tsk-2fa42241…`, `agent_error`), and the BUG-107 publish
failure (`pub-f03ad672…`). Nothing is hidden.
