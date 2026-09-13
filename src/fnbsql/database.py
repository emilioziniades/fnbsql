import logging
import sqlite3
from dataclasses import astuple, dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Transaction:
    date: str
    amount: float
    description: str
    debit: bool
    account_number: str


class Database:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._setup()

    def _setup(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                debit INTEGER NOT NULL CHECK (debit IN (0, 1)),
                account_number TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS transactions_unique
            ON transactions (date, amount, description, debit, account_number)
            """
        )

    def insert(self, transaction: Transaction) -> None:
        if not isinstance(transaction, Transaction):
            raise TypeError("Database.insert() requires a Transaction")

        try:
            self._connection.execute(
                "INSERT INTO transactions "
                "(date, amount, description, debit, account_number) "
                "VALUES (?, ?, ?, ?, ?)",
                astuple(transaction),
            )
        except sqlite3.IntegrityError:
            LOGGER.warning("Duplicate transaction was not inserted: %s", transaction)

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
