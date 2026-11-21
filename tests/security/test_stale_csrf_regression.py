"""T075 (part 2) stale-CSRF and revoked-session regression: pure domain denials.

A superseded CSRF context (``rotated_at`` stamped by :func:`supersede`) must
deny every later :func:`verify_csrf` call for its old token, and rotation
must invalidate the previous raw token while the fresh token verifies.
Symmetrically, a revoked session record denies :func:`verify_session`
immediately, an expired one denies at ``expires_at`` plus one second, and
re-revoking (or re-superseding) an already-stamped record is idempotent.
These are pure identity-domain behaviors: no database, no migrations.
"""

import unittest
from datetime import datetime, timedelta, timezone

from opsledger.core.clock import FixedClock
from opsledger.core.errors import ValidationError
from opsledger.identity.csrf import (
    CSRF_TTL_SECONDS,
    issue_context,
    rotate_context,
    supersede,
    verify_csrf,
)
from opsledger.identity.sessions import (
    SESSION_TTL_SECONDS,
    create_session,
    revoke_session,
    verify_session,
)


def _at(seconds: int) -> FixedClock:
    return FixedClock(
        datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    )


class StaleCsrfRegressionTests(unittest.TestCase):
    """Regression coverage for stale CSRF contexts and dead sessions (T075 part 2)."""

    def test_superseded_csrf_and_revoked_or_expired_sessions_are_denied(self):
        raw, rec = create_session("usr-1", clock=_at(0))
        self.assertTrue(verify_session(raw, rec, clock=_at(1)))
        rec2 = revoke_session(rec, clock=_at(2))
        self.assertFalse(verify_session(raw, rec2, clock=_at(3)))
        self.assertEqual(revoke_session(rec2, clock=_at(4)).revoked_at, rec2.revoked_at)
        self.assertFalse(verify_session(raw, rec, clock=_at(SESSION_TTL_SECONDS + 1)))
        with self.assertRaises(ValidationError) as raised:
            create_session("", clock=_at(0))
        self.assertEqual("user_id must not be empty", str(raised.exception))
        with self.assertRaises(ValidationError) as raised:
            create_session("usr", clock=_at(0), ttl_seconds=0)
        self.assertEqual(
            "ttl_seconds must be between 1 and 2592000", str(raised.exception)
        )
        craw, cctx = issue_context(clock=_at(0))
        self.assertTrue(verify_csrf(craw, cctx, clock=_at(1)))
        sup = supersede(cctx, clock=_at(2))
        self.assertFalse(verify_csrf(craw, sup, clock=_at(3)))
        self.assertEqual(supersede(sup, clock=_at(4)).rotated_at, sup.rotated_at)
        raw2, ctx2 = issue_context(clock=_at(5))
        self.assertTrue(verify_csrf(raw2, ctx2, clock=_at(5)))
        raw3, ctx3 = rotate_context(ctx2, clock=_at(6))
        self.assertFalse(verify_csrf(raw2, ctx3, clock=_at(7)))
        self.assertTrue(verify_csrf(raw3, ctx3, clock=_at(7)))
        sup_ctx2 = supersede(ctx2, clock=_at(7))
        with self.assertRaises(ValidationError) as raised:
            rotate_context(sup_ctx2, clock=_at(8))
        self.assertEqual(
            "previous context has already been rotated", str(raised.exception)
        )
        with self.assertRaises(ValidationError) as raised:
            rotate_context(sup, clock=_at(8))
        self.assertEqual(
            "previous context has already been rotated", str(raised.exception)
        )
        self.assertFalse(verify_csrf(craw, cctx, clock=_at(CSRF_TTL_SECONDS + 1)))


if __name__ == "__main__":
    unittest.main()
