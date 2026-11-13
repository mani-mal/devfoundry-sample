"""Unit tests (T012): organization identity context guards.

Pure unit tests -- no real database. Rows and the connection are stubbed.
The core acceptance is the no-leak rule: a missing record and a record owned
by another organization are indistinguishable (one canonical error message).
"""

import unittest

from opsledger.core.errors import NotFoundError, ValidationError
from opsledger.core.context import (
    OrganizationContext,
    require_context,
    require_owned,
    scoped_all,
    scoped_first,
)


class _Cursor:
    """Fake cursor whose fetchone/fetchall serve a canned sequence of rows."""

    def __init__(self, rows):
        self._rows = list(rows)

    def fetchone(self):
        if self._rows:
            return self._rows.pop(0)
        return None

    def fetchall(self):
        rows = list(self._rows)
        self._rows.clear()
        return rows


class _FakeConn:
    """Small fake conn class: execute returns a canned sequence of cursors."""

    def __init__(self, cursors):
        self._cursors = list(cursors)

    def execute(self, sql, params=()):
        return self._cursors.pop(0)


class ContextTests(unittest.TestCase):
    def test_t1_require_context_passes_and_rejects(self):
        context = OrganizationContext(organization_id="org-aaa")
        self.assertIs(require_context(context), context)
        with self.assertRaises(ValidationError):
            require_context("org-aaa")
        with self.assertRaises(ValidationError):
            require_context(None)
        with self.assertRaises(ValidationError):
            require_context(OrganizationContext(organization_id=""))

    def test_t2_require_owned_returns_row_for_owning_org(self):
        context = OrganizationContext(organization_id="org-aaa")
        dict_row = {"id": "wo-1", "organization_id": "org-aaa"}
        self.assertIs(require_owned(context, dict_row), dict_row)

        class _AttrRow:
            organization_id = "org-aaa"

        attr_row = _AttrRow()
        self.assertIs(require_owned(context, attr_row), attr_row)

    def test_t3_require_owned_not_found_message_equal_no_leak(self):
        context = OrganizationContext(organization_id="org-aaa")

        class _ForeignRow:
            organization_id = "org-bbb"

        with self.assertRaises(NotFoundError) as missing:
            require_owned(context, None)
        with self.assertRaises(NotFoundError) as foreign:
            require_owned(context, _ForeignRow())
        self.assertEqual("resource not found", missing.exception.args[0])
        self.assertEqual("resource not found", foreign.exception.args[0])
        self.assertEqual(missing.exception.args[0], foreign.exception.args[0])

    def test_t4_require_owned_custom_label(self):
        context = OrganizationContext(organization_id="org-aaa")
        with self.assertRaises(NotFoundError) as ctx:
            require_owned(context, None, label="work order")
        self.assertEqual("work order not found", ctx.exception.args[0])

    def test_t5_scoped_first_and_scoped_all_via_fake_conn(self):
        context = OrganizationContext(organization_id="org-aaa")
        owned = {"id": "wo-1", "organization_id": "org-aaa"}
        foreign = {"id": "wo-2", "organization_id": "org-bbb"}
        other_owned = {"id": "wo-3", "organization_id": "org-aaa"}

        self.assertIs(
            scoped_first(_FakeConn([_Cursor([owned])]), context, "SELECT 1"),
            owned,
        )
        self.assertIsNone(
            scoped_first(_FakeConn([_Cursor([foreign])]), context, "SELECT 1")
        )
        self.assertIsNone(
            scoped_first(_FakeConn([_Cursor([])]), context, "SELECT 1")
        )

        result = scoped_all(
            _FakeConn([_Cursor([owned, foreign, other_owned])]),
            context,
            "SELECT 1",
        )
        self.assertEqual([owned, other_owned], result)

    def test_t6_actor_id_optional_and_carried_through(self):
        context = OrganizationContext(organization_id="org-aaa")
        self.assertIsNone(context.actor_id)
        with_actor = OrganizationContext(
            organization_id="org-aaa", actor_id="u-1"
        )
        carried = require_context(with_actor)
        self.assertIs(carried, with_actor)
        self.assertEqual("u-1", carried.actor_id)

    def test_t7_require_owned_row_without_organization_id_raises(self):
        context = OrganizationContext(organization_id="org-aaa")
        with self.assertRaises(NotFoundError):
            require_owned(context, {"id": "wo-1"})

        class _BareRow:
            id = "wo-1"

        with self.assertRaises(NotFoundError):
            require_owned(context, _BareRow())

    def test_t8_require_context_rejects_non_str_organization_id(self):
        with self.assertRaises(ValidationError):
            require_context(OrganizationContext(organization_id=42))


if __name__ == "__main__":
    unittest.main()
