"""SQLite persistence foundation for OpsLedger services.

Connection policy
=================

Connections are *never* shared across threads: each thread creates its own
connection with :func:`connect` and uses it on the creating thread only.
The factory keeps the standard-library default ``check_same_thread=True``,
so SQLite itself raises if a connection is used from a different thread.

Every connection is opened in explicit-transaction mode
(``isolation_level=None``): nothing is implicitly started or committed, so
all writes go through :func:`transaction` (or an explicit ``BEGIN``). This
is what keeps commit and rollback behavior deterministic and auditable.

PRAGMAs applied at open time:

- ``foreign_keys=ON`` — FK constraints are enforced on this connection.
- ``journal_mode=WAL`` — durable, concurrent-friendly journal.
- ``synchronous=NORMAL`` — the WAL-recommended durability level.

Database errors from :mod:`sqlite3` (for example ``IntegrityError`` or
``OperationalError``) are re-raised as-is: they are never swallowed and
never converted into application errors.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from types import TracebackType

from .errors import ConflictError

__all__ = ["connect", "transaction"]

_PRAGMA_STATEMENTS = (
    "PRAGMA foreign_keys=ON",
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
)


class _OpsLedgerConnection(sqlite3.Connection):
    """Connection profile that can carry the active-transaction flag.

    A Python-level subclass is the only safe way to attach per-connection
    state to a ``sqlite3.Connection``: plain connections reject attribute
    assignment and cannot be weak-referenced. The flag lives on the
    instance, so the nested-transaction guard is exact per connection.
    """

    __slots__ = ("_opsledger_active_transaction",)


class _Transaction:
    """Context manager driving one IMMEDIATE transaction on ``conn``.

    Acquired through :func:`transaction`; see that function for behavior.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        if getattr(self._conn, "_opsledger_active_transaction", False):
            raise ConflictError(
                "nested transactions are not supported; "
                "start the inner transaction after the outer one exits"
            )
        self._conn._opsledger_active_transaction = True
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except BaseException:
            self._conn._opsledger_active_transaction = False
            raise
        return self._conn

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self._conn._opsledger_active_transaction = False
        if exc is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        return False


def connect(path: str) -> sqlite3.Connection:
    """Open a SQLite connection to ``path`` with the OpsLedger profile.

    The returned connection (a :class:`sqlite3.Connection` subclass) has
    ``foreign_keys=ON``, ``journal_mode=WAL``, ``synchronous=NORMAL``, and
    ``row_factory=sqlite3.Row``. Connections are never shared across
    threads: use each connection on its creating thread only. Use
    :func:`transaction` for every write.
    """
    conn = sqlite3.connect(
        path, check_same_thread=True, isolation_level=None,
        factory=_OpsLedgerConnection,
    )
    conn.row_factory = sqlite3.Row
    for statement in _PRAGMA_STATEMENTS:
        conn.execute(statement)
    return conn


def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block inside one IMMEDIATE transaction on ``conn``.

    On clean exit the transaction is committed; on any exception it is
    rolled back and the original error is re-raised. Nested use raises
    :class:`ConflictError` with stable code ``"conflict"``. sqlite3 errors
    (``IntegrityError``, ``OperationalError``) propagate unchanged.

    Usage::

        with transaction(conn) as tx:
            tx.execute("INSERT ...")
    """
    return _Transaction(conn)
