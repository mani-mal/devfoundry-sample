# Campaign scaffolding

Private local artifacts for the DevFoundry campaign (`opsledger-run-001`).
Everything here is operator-side; it is never sent to the DevFoundry server
except the rendered request files the driver places in `requests/`.

## What each subdir is

- `driver/` — the campaign driver's local code: preflight helper, evidence
  journal, request template/renderer, and a thin DevFoundry CLI adapter with
  a dry-run mode. Offline-tested only (`campaign/driver/tests/`).
- `requests/` — rendered task request files land here (`.gitkeep` for now).
- `journal/` — `events.jsonl` is append-only private local evidence (JSONL,
  one event per line) plus `index.json`, a rebuildable projection written
  atomically via temp file + `os.replace`.
- `evidence/` — per-attempt evidence artifacts land here.
- `acceptance/` — human review / acceptance records land here.
- `platform_cases/` — recorded platform state snapshots land here.
- `reports/` — preflight and campaign reports (markdown) land here.

## Credentials

No credentials, tokens, or passwords here — ever. `config.example.json` is a
non-secret configuration shape with placeholders; the operator supplies the
secret source (env or operator-controlled file) at run time. The driver's
live mode requires operator authorization; its dry-run fixtures are always
labelled `fixture` and never claim a live task.

## Resume

Resuming a campaign = rebuild the projection and reload complete records:

```python
from pathlib import Path
from campaign.driver import journal

events = journal.load_events(Path("campaign/journal/events.jsonl"))
journal.rebuild_index(Path("campaign/journal/events.jsonl"), Path("campaign/journal/index.json"))
```

`load_events` skips a malformed/partial final line (crash mid-append) with a
warning to stderr, so resume always rebuilds from complete records only.
`journal/events.jsonl` is append-only: never rewrite or prune it locally.
