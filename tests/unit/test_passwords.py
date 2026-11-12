"""Tests for password-hash records and offline user provisioning (T009)."""

import hashlib
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.identity import (  # noqa: E402
    PROTOCOL_VERSION,
    PasswordHash,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
    ScryptParams,
    from_row,
    hash_password,
    provision_user,
    provision_user_sql,
    scrypt_unavailable,
    to_row,
    verify_password,
)
from opsledger.core.db import connect  # noqa: E402
from opsledger.core.errors import ValidationError  # noqa: E402

RFC3339_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class StubClock:
    def now(self):
        return datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)

    def timestamp(self):
        return "2026-11-06T12:00:00Z"


class SharedStubRng:
    """Deterministic rng: one distinct fixed byte pattern per call.

    Shared across several hash_password calls in a test, so each call
    yields a different salt (bytes(1), bytes(2), ...).
    """

    def __init__(self):
        self.calls = 0

    def __call__(self, nbytes):
        self.calls += 1
        return bytes([self.calls]) * nbytes


class _RaisingScrypt:
    def __enter__(self):
        self._original = hashlib.scrypt

        def raising_scrypt(*args, **kwargs):
            raise ValueError("OpenSSL/PRF unsupported")

        hashlib.scrypt = raising_scrypt
        return self

    def __exit__(self, exc_type, exc, tb):
        hashlib.scrypt = self._original
        return False


def raised_scrypt():
    return _RaisingScrypt()


class HashRecordTests(unittest.TestCase):
    def test_correct_password_verifies_and_wrong_fails(self):
        record = hash_password("correct horse", clock=StubClock(), rng=SharedStubRng())

        self.assertTrue(verify_password("correct horse", record))
        self.assertFalse(verify_password("battery staple", record))

    def test_wrong_password_fails_both_directions(self):
        first = hash_password("alpha", clock=StubClock(), rng=SharedStubRng())
        second = hash_password("beta", clock=StubClock(), rng=SharedStubRng())

        self.assertTrue(verify_password("beta", second))
        self.assertFalse(verify_password("alpha", second))
        self.assertFalse(verify_password("beta", first))

    def test_two_hashes_of_same_password_have_different_salts_and_hashes(self):
        rng = SharedStubRng()
        first = hash_password("same", clock=StubClock(), rng=rng)
        second = hash_password("same", clock=StubClock(), rng=rng)

        self.assertNotEqual(first.salt, second.salt)
        self.assertNotEqual(first.hash, second.hash)
        self.assertTrue(verify_password("same", first))
        self.assertTrue(verify_password("same", second))

    def test_every_hash_record_stores_protocol_version_and_params(self):
        record = hash_password("proto", clock=StubClock(), rng=SharedStubRng())

        self.assertEqual(record.protocol_version, PROTOCOL_VERSION)
        self.assertEqual(record.protocol_version, 1)
        self.assertEqual(record.params, ScryptParams(n=16384, r=8, p=1))
        self.assertEqual(record.params.n, SCRYPT_N)
        self.assertEqual(record.params.r, SCRYPT_R)
        self.assertEqual(record.params.p, SCRYPT_P)

    def test_custom_params_are_recorded_and_both_verify(self):
        params = ScryptParams(n=2**10, r=4, p=2)
        rng = SharedStubRng()
        first = hash_password(
            "custom", params=params, clock=StubClock(), rng=rng
        )
        second = hash_password(
            "custom", params=params, clock=StubClock(), rng=rng
        )

        self.assertEqual(first.params, params)
        self.assertEqual(second.params, params)
        self.assertNotEqual(first.salt, second.salt)
        self.assertTrue(verify_password("custom", first))
        self.assertTrue(verify_password("custom", second))

    def test_record_shape_is_frozen_with_hex_lengths_and_timestamp(self):
        record = hash_password("shape", clock=StubClock(), rng=SharedStubRng())

        self.assertIsInstance(record, PasswordHash)
        self.assertEqual(len(record.salt), 32)
        self.assertEqual(len(record.hash), 128)
        self.assertTrue(RFC3339_Z_PATTERN.match(record.created_at))
        with self.assertRaises(Exception):
            record.salt = "tampered"

    def test_empty_password_rejected(self):
        with self.assertRaises(ValidationError):
            hash_password("")


class ScryptParamsValidationTests(unittest.TestCase):
    def test_n_must_be_power_of_two_greater_than_one(self):
        for bad_n in (1, 0, -2, 3, 12, 1000, SCRYPT_N - 1):
            with self.assertRaises(ValidationError):
                ScryptParams(n=bad_n).validate()

    def test_valid_n_accepted_including_shipped_factor(self):
        for good_n in (2, 4, 1024, SCRYPT_N):
            ScryptParams(n=good_n).validate()

    def test_r_and_p_must_be_at_least_one(self):
        with self.assertRaises(ValidationError):
            ScryptParams(r=0).validate()
        with self.assertRaises(ValidationError):
            ScryptParams(p=0).validate()
        with self.assertRaises(ValidationError):
            ScryptParams(n=3, r=-1, p=-1).validate()

    def test_shipped_factors_are_constants(self):
        self.assertEqual((SCRYPT_N, SCRYPT_R, SCRYPT_P), (16384, 8, 1))


class VerifyTamperTests(unittest.TestCase):
    def make_record(self):
        return hash_password("secret", clock=StubClock(), rng=SharedStubRng())

    def test_tampered_hash_fails_verification_without_exception_escape(self):
        record = self.make_record()
        flipped = ("0" if record.hash[0] == "f" else "f") + record.hash[1:]
        tampered = replace(record, hash=flipped)

        self.assertFalse(verify_password("secret", tampered))

    def test_tampered_salt_fails_verification(self):
        record = self.make_record()
        flipped = ("0" if record.salt[0] == "f" else "f") + record.salt[1:]
        tampered = replace(record, salt=flipped)

        self.assertFalse(verify_password("secret", tampered))

    def test_unknown_protocol_version_raises_validation_error_on_verify(self):
        record = self.make_record()
        future = replace(record, protocol_version=PROTOCOL_VERSION + 1)

        with self.assertRaises(ValidationError):
            verify_password("secret", future)

    def test_malformed_record_bad_hex_raises_validation_error(self):
        record = self.make_record()
        for malformed in (
            replace(record, salt="zz"),
            replace(record, hash="not-hex"),
            replace(record, salt=record.salt[:-1]),
            replace(record, hash=record.hash[:-1]),
        ):
            with self.assertRaises(ValidationError):
                verify_password("secret", malformed)


class ScryptUnavailableTests(unittest.TestCase):
    def test_scrypt_unavailable_true_when_hashlib_raises_value_error(self):
        with raised_scrypt():
            self.assertTrue(scrypt_unavailable())
            with self.assertRaises(ValidationError):
                hash_password("secret")

    def test_scrypt_unavailable_false_when_hashlib_works(self):
        self.assertFalse(scrypt_unavailable())


class ProvisionUserTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.conn = connect(str(self.tmp_path / "db.sqlite"))
        self.addCleanup(self.conn.close)
        self.conn.execute(
            "CREATE TABLE users ("
            " id TEXT PRIMARY KEY,"
            " email TEXT NOT NULL UNIQUE,"
            " display_name TEXT NOT NULL,"
            " created_at TEXT NOT NULL,"
            " salt TEXT NOT NULL,"
            " hash TEXT NOT NULL,"
            " n INTEGER NOT NULL,"
            " r INTEGER NOT NULL,"
            " p INTEGER NOT NULL,"
            " protocol_version INTEGER NOT NULL)"
        )

    def stored_users(self):
        return self.conn.execute(
            "SELECT id, email, display_name, created_at, salt, hash, n,"
            " p, protocol_version FROM users"
        ).fetchall()

    def test_inserts_row_with_hash_fields_and_normalizes_email_to_lowercase(self):
        record = provision_user(
            self.conn,
            user_id="user-1",
            email="Dev@Example.COM",
            display_name="Dev",
            password="correct horse",
            clock=StubClock(),
            rng=SharedStubRng(),
        )

        users = self.stored_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["id"], "user-1")
        self.assertEqual(users[0]["email"], "dev@example.com")
        self.assertEqual(users[0]["display_name"], "Dev")
        self.assertEqual(users[0]["created_at"], record.created_at)
        self.assertEqual(users[0]["salt"], record.salt)
        self.assertEqual(users[0]["hash"], record.hash)
        self.assertEqual(users[0]["n"], SCRYPT_N)
        self.assertEqual(users[0]["protocol_version"], 1)
        self.assertEqual(record.user_id, "user-1")
        self.assertTrue(verify_password("correct horse", record))
        self.assertFalse(verify_password("nope", record))

    def test_duplicate_email_raises_validation_error_with_one_row_stored(self):
        provision_user(
            self.conn,
            user_id="user-1",
            email="dev@example.com",
            display_name="Dev",
            password="alpha",
            clock=StubClock(),
            rng=SharedStubRng(),
        )

        with self.assertRaises(ValidationError):
            provision_user(
                self.conn,
                user_id="user-2",
                email="  Dev@Example.com  ",
                display_name="Other",
                password="beta",
                clock=StubClock(),
                rng=SharedStubRng(),
            )

        rows = self.stored_users()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "user-1")

    def test_scrypt_unavailable_provisioning_raises_and_never_stores_a_row(self):
        with raised_scrypt():
            with self.assertRaises(ValidationError):
                provision_user(
                    self.conn,
                    user_id="user-1",
                    email="dev@example.com",
                    display_name="Dev",
                    password="correct horse",
                    clock=StubClock(),
                    rng=SharedStubRng(),
                )
            self.assertTrue(scrypt_unavailable())

        rows = self.stored_users()
        self.assertEqual(len(rows), 0)

    def test_malformed_email_rejected_without_store(self):
        for bad_email in ("no-at-sign", "two@@signs.dev", "@empty.local"):
            with self.assertRaises(ValidationError):
                provision_user(
                    self.conn,
                    user_id="user-bad",
                    email=bad_email,
                    display_name="Dev",
                    password="pw",
                    clock=StubClock(),
                    rng=SharedStubRng(),
                )

        rows = self.stored_users()
        self.assertEqual(len(rows), 0)


class RowMappingTests(unittest.TestCase):
    def test_to_row_and_from_row_round_trip_hash_columns(self):
        record = hash_password("round trip", clock=StubClock(), rng=SharedStubRng())
        row = to_row(record)

        for column in ("id", "email", "display_name", "created_at", "salt",
                       "hash", "n", "r", "p", "protocol_version"):
            self.assertIn(column, row)
        self.assertEqual(row["id"], record.user_id)
        self.assertEqual(row["created_at"], record.created_at)
        self.assertEqual(row["salt"], record.salt)
        self.assertEqual(row["hash"], record.hash)
        self.assertEqual(row["n"], SCRYPT_N)
        self.assertEqual(row["r"], SCRYPT_R)
        self.assertEqual(row["p"], SCRYPT_P)
        self.assertEqual(row["protocol_version"], 1)

        restored = from_row(row)
        self.assertEqual(restored, record)
        self.assertTrue(verify_password("round trip", restored))

    def test_from_row_with_foreign_dict_maps_to_record(self):
        row = {
            "id": "user-9",
            "email": "",
            "display_name": "",
            "created_at": "2026-11-06T12:00:00Z",
            "salt": "ab" * 32,
            "hash": "cd" * 64,
            "n": 16384,
            "r": 8,
            "p": 1,
            "protocol_version": 1,
        }

        restored = from_row(row)

        self.assertEqual(restored.user_id, "user-9")
        self.assertEqual(restored.salt, "ab" * 32)
        self.assertEqual(restored.hash, "cd" * 64)
        self.assertEqual(restored.params, ScryptParams(n=16384, r=8, p=1))
        self.assertEqual(restored.protocol_version, 1)


if __name__ == "__main__":
    unittest.main()
