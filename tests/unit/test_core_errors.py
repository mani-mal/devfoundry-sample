"""Tests for the shared application error types (T001)."""

import sys
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.errors import (  # noqa: E402
    ApplicationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


class ApplicationErrorTests(unittest.TestCase):
    def test_carries_code_public_message_and_fields(self):
        error = ApplicationError(
            "Site is read only",
            code="site_read_only",
            fields={"site": "cannot be modified while archived"},
        )
        self.assertEqual(error.code, "site_read_only")
        self.assertEqual(str(error), "Site is read only")
        self.assertEqual(
            error.fields, {"site": "cannot be modified while archived"}
        )

    def test_default_code_is_stable(self):
        self.assertEqual(
            ApplicationError("boom").code, "application_error"
        )

    def test_fields_default_to_empty_dict(self):
        self.assertEqual(ApplicationError("boom").fields, {})

    def test_payload_includes_code_and_message(self):
        payload = ApplicationError("boom", code="oops").to_payload()
        self.assertEqual(payload, {"code": "oops", "message": "boom"})

    def test_payload_omits_fields_when_absent(self):
        self.assertNotIn("fields", ApplicationError("boom").to_payload())

    def test_payload_includes_safe_field_details(self):
        payload = ValidationError(
            "name is invalid", fields={"name": "required"}
        ).to_payload()
        self.assertEqual(
            payload,
            {
                "code": "validation_error",
                "message": "name is invalid",
                "fields": {"name": "required"},
            },
        )

    def test_message_does_not_contain_traceback_markers(self):
        try:
            raise ValueError("internal detail")
        except ValueError:
            error = ApplicationError("Something went wrong")
        self.assertNotIn("Traceback", str(error))
        self.assertNotIn("ValueError", str(error))
        self.assertNotIn("internal detail", str(error))

    def test_is_exception(self):
        self.assertIsInstance(ValidationError("x"), Exception)


class SubclassDefaultCodeTests(unittest.TestCase):
    def test_validation_error_default_code(self):
        self.assertEqual(ValidationError("x").code, "validation_error")

    def test_not_found_error_default_code(self):
        self.assertEqual(NotFoundError("x").code, "not_found")

    def test_permission_denied_error_default_code(self):
        self.assertEqual(
            PermissionDeniedError("x").code, "permission_denied"
        )

    def test_conflict_error_default_code(self):
        self.assertEqual(ConflictError("x").code, "conflict")

    def test_subclasses_are_application_errors(self):
        for cls in (
            ValidationError,
            NotFoundError,
            PermissionDeniedError,
            ConflictError,
        ):
            self.assertTrue(issubclass(cls, ApplicationError))

    def test_subclass_code_can_be_overridden(self):
        error = NotFoundError("x", code="work_order_not_found")
        self.assertEqual(error.code, "work_order_not_found")


if __name__ == "__main__":
    unittest.main()
