from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
import logging
from pathlib import Path
import re

import pdfplumber
from pdfplumber.page import Page
from pdfplumber.pdf import PDF

from fnbsql.database import Transaction


LOGGER = logging.getLogger(__name__)
STATEMENT_PERIOD_RE = re.compile(
    r"Statement Period\s*:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})"
    r"\s+to\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.IGNORECASE,
)
ACCOUNT_NUMBER_RE = re.compile(r"FNB .* Account\s*:\s*(\d+)", re.IGNORECASE)
TRANSACTION_DATE_RE = re.compile(r"^\d{2}\s+[A-Za-z]{3}$")
OPENING_BALANCE_RE = re.compile(r"Opening Balance\s+([\d,]+\.\d{2})(Cr|Dr)?")
CLOSING_BALANCE_RE = re.compile(r"Closing Balance\s+([\d,]+\.\d{2})(Cr|Dr)?")
type TableRow = list[str | None]


class PdfStatement:
    def __init__(self, path: Path) -> None:
        self.path = path
        with pdfplumber.open(path) as pdf:
            period = self._statement_period(pdf.pages[0])
            self.transactions = list(self._extract_transactions(pdf, period))
            self._validate(pdf.pages[0], period)

    @staticmethod
    def _statement_period(page: Page) -> tuple[date, date]:
        match = STATEMENT_PERIOD_RE.search(page.extract_text() or "")
        if match is None:
            raise ValueError("Could not find the statement period on the first page")

        start = datetime.strptime(match.group(1), "%d %B %Y").date()
        end = datetime.strptime(match.group(2), "%d %B %Y").date()
        if start > end:
            raise ValueError("Statement period starts after it ends")
        return start, end

    @staticmethod
    def _account_number(page: Page) -> str:
        match = ACCOUNT_NUMBER_RE.search(page.extract_text() or "")
        if match is None:
            raise ValueError("Could not find the account number on the first page")
        return match.group(1)

    @staticmethod
    def _transaction_from_row(
        row: TableRow, period: tuple[date, date], account: str
    ) -> Transaction | None:
        if (
            len(row) < 4
            or not row[0]
            or not TRANSACTION_DATE_RE.fullmatch(row[0])
        ):
            return None

        start, end = period
        possible_dates = (
            datetime.strptime(f"{row[0]} {year}", "%d %b %Y").date()
            for year in range(start.year, end.year + 1)
        )
        transaction_dates = [value for value in possible_dates if start <= value <= end]
        if len(transaction_dates) != 1:
            raise ValueError(
                f"Could not resolve transaction date {row[0]!r} within "
                f"statement period {start} to {end}"
            )

        transaction_date = transaction_dates[0].isoformat()
        raw_amount = row[2].replace(",", "").strip()
        debit = not raw_amount.lower().endswith("cr")
        amount = float(re.sub(r"(?:cr|dr)$", "", raw_amount, flags=re.IGNORECASE))
        return Transaction(
            transaction_date, amount, (row[1] or "").strip(), debit, account
        )

    def _extract_transactions(
        self, pdf: PDF, period: tuple[date, date]
    ) -> Iterator[Transaction]:
        account = self._account_number(pdf.pages[0])
        for page in pdf.pages:
            tables = page.extract_tables(
                {
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "text",
                    "min_words_horizontal": 4,
                    "snap_x_tolerance": 4,
                    "snap_y_tolerance": 4,
                }
            )
            for table in tables:
                for row in table:
                    transaction = self._transaction_from_row(row, period, account)
                    if transaction is not None:
                        yield transaction

    @staticmethod
    def _extract_balance(pattern: re.Pattern[str], page_text: str) -> Decimal:
        match = pattern.search(page_text)
        if match is None:
            raise ValueError("Could not find opening or closing balance on first page")

        balance = Decimal(match.group(1).replace(",", ""))
        return -balance if match.group(2) == "Dr" else balance

    def _validate(self, first_page: Page, period: tuple[date, date]) -> None:
        start, end = period
        invalid_dates = [
            transaction.date
            for transaction in self.transactions
            if not start <= date.fromisoformat(transaction.date) <= end
        ]
        if invalid_dates:
            raise ValueError(
                f"Transactions fall outside statement period {start} to {end}: "
                f"{invalid_dates}"
            )
        LOGGER.info(
            "Validated %d transaction dates within statement period %s to %s",
            len(self.transactions),
            start,
            end,
        )

        page_text = first_page.extract_text() or ""
        opening_balance = self._extract_balance(OPENING_BALANCE_RE, page_text)
        closing_balance = self._extract_balance(CLOSING_BALANCE_RE, page_text)
        transaction_total = sum(
            (
                -Decimal(str(transaction.amount))
                if transaction.debit
                else Decimal(str(transaction.amount))
                for transaction in self.transactions
            ),
            start=Decimal(),
        )
        calculated_closing_balance = opening_balance + transaction_total

        if calculated_closing_balance != closing_balance:
            raise ValueError(
                "Statement does not balance: "
                f"opening balance {opening_balance:.2f} + transactions "
                f"{transaction_total:.2f} = {calculated_closing_balance:.2f}, "
                f"expected {closing_balance:.2f}"
            )
        LOGGER.info(
            "Validated statement balance: %s + %s = %s",
            opening_balance,
            transaction_total,
            closing_balance,
        )
