import logging
import sqlite3
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path
from types import TracebackType
from typing import Self

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Transaction:
    date: Date
    amount: int
    description: str
    debit: bool


@dataclass(frozen=True, slots=True)
class Statement:
    account_number: str
    period_start: Date
    period_end: Date
    opening_balance: int
    closing_balance: int
    transactions: tuple[Transaction, ...]


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._setup()
        LOGGER.info("Using database at %s", path.resolve())

    def _setup(self) -> None:
        self._connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS statements (
                id INTEGER PRIMARY KEY,
                account_number TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                opening_balance INTEGER NOT NULL,
                closing_balance INTEGER NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS statements_unique
            ON statements (account_number, period_start, period_end);

            CREATE TABLE IF NOT EXISTS transactions (
                statement_id INTEGER NOT NULL REFERENCES statements(id),
                position INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount INTEGER NOT NULL,
                description TEXT NOT NULL,
                debit INTEGER NOT NULL CHECK (debit IN (0, 1)),
                PRIMARY KEY (statement_id, position)
            );
            """
        )

    def insert(self, statement: Statement) -> None:
        if not isinstance(statement, Statement):
            raise TypeError("Database.insert() requires a Statement")
        try:
            cursor = self._connection.execute(
                """
                INSERT INTO statements (
                    account_number,
                    period_start,
                    period_end,
                    opening_balance,
                    closing_balance
                )
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    statement.account_number,
                    statement.period_start.isoformat(),
                    statement.period_end.isoformat(),
                    statement.opening_balance,
                    statement.closing_balance,
                ),
            )
        except sqlite3.IntegrityError:
            LOGGER.warning(
                "Duplicate statement was not inserted: account %s, period %s to %s",
                statement.account_number,
                statement.period_start,
                statement.period_end,
            )
            return

        returned_row = cursor.fetchone()
        if returned_row is None:
            raise RuntimeError("SQLite did not return the inserted statement ID")
        statement_id = returned_row[0]
        for position, transaction in enumerate(statement.transactions):
            self._insert_transaction(statement_id, position, transaction)

    def _insert_transaction(
        self, statement_id: int, position: int, transaction: Transaction
    ) -> None:
        if not isinstance(transaction, Transaction):
            raise TypeError("Database transactions must be Transaction instances")
        self._connection.execute(
            """
            INSERT INTO transactions (
                statement_id,
                position,
                date,
                amount,
                description,
                debit
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                statement_id,
                position,
                transaction.date.isoformat(),
                transaction.amount,
                transaction.description,
                transaction.debit,
            ),
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._connection.__exit__(exception_type, exception, traceback)
        self._connection.close()
        return False
