"""Campaign driver: preflight, journal, request rendering, dry-run CLI adapter.

This code is offline-tested only. It never performs live DevFoundry calls in
tests; the adapter's live mode requires an operator-injected runner callable
plus operator authorization and stored credentials (never embedded here).
"""
