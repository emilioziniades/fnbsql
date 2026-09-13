import logging
import re
import time
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber
from pdfplumber.pdf import PDF

from fnbsql.database import Statement, Transaction

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


def parse_date(value: str, format_string: str) -> date:
    parsed = time.strptime(value, format_string)
    return date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday)


class PdfStatement:
    def __init__(self, path: Path) -> None:
        self.path = path
        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            self.period_start, self.period_end = self._extract_statement_period(
                first_page_text
            )
            self.account_number = self._extract_account_number(first_page_text)
            self.opening_balance = self._extract_balance(
                OPENING_BALANCE_RE, first_page_text
            )
            self.closing_balance = self._extract_balance(
                CLOSING_BALANCE_RE, first_page_text
            )
            self.transactions = list(self._extract_transactions(pdf))
            self._validate()
            self.statement = Statement(
                account_number=self.account_number,
                period_start=self.period_start,
                period_end=self.period_end,
                opening_balance=self.opening_balance,
                closing_balance=self.closing_balance,
                transactions=tuple(self.transactions),
            )

    @staticmethod
    def _extract_statement_period(page_text: str) -> tuple[date, date]:
        match = STATEMENT_PERIOD_RE.search(page_text)
        if match is None:
            raise ValueError("Could not find the statement period on the first page")

        start = parse_date(match.group(1), "%d %B %Y")
        end = parse_date(match.group(2), "%d %B %Y")
        if start > end:
            raise ValueError("Statement period starts after it ends")
        return start, end

    @staticmethod
    def _extract_account_number(page_text: str) -> str:
        match = ACCOUNT_NUMBER_RE.search(page_text)
        if match is None:
            raise ValueError("Could not find the account number on the first page")
        return match.group(1)

    @staticmethod
    def _transaction_from_row(
        row: TableRow,
        period_start: date,
        period_end: date,
    ) -> Transaction | None:
        if len(row) < 4:
            return None

        date_text = row[0]
        amount_text = row[2]
        if (
            not date_text
            or not amount_text
            or not TRANSACTION_DATE_RE.fullmatch(date_text)
        ):
            return None

        possible_dates = (
            parse_date(f"{date_text} {year}", "%d %b %Y")
            for year in range(period_start.year, period_end.year + 1)
        )
        transaction_dates = [
            value for value in possible_dates if period_start <= value <= period_end
        ]
        if len(transaction_dates) != 1:
            raise ValueError(
                f"Could not resolve transaction date {date_text!r} within "
                f"statement period {period_start} to {period_end}"
            )

        raw_amount = amount_text.replace(",", "").strip()
        debit = not raw_amount.lower().endswith("cr")
        decimal_amount = Decimal(
            re.sub(r"(?:cr|dr)$", "", raw_amount, flags=re.IGNORECASE)
        )
        amount = int(decimal_amount * 100)
        return Transaction(
            transaction_dates[0],
            amount,
            (row[1] or "").strip(),
            debit,
        )

    def _extract_transactions(self, pdf: PDF) -> Iterator[Transaction]:
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
                    transaction = self._transaction_from_row(
                        row,
                        self.period_start,
                        self.period_end,
                    )
                    if transaction is not None:
                        yield transaction

    @staticmethod
    def _extract_balance(pattern: re.Pattern[str], page_text: str) -> int:
        match = pattern.search(page_text)
        if match is None:
            raise ValueError("Could not find opening or closing balance on first page")

        balance = int(Decimal(match.group(1).replace(",", "")) * 100)
        return -balance if match.group(2) == "Dr" else balance

    def _validate(self) -> None:
        invalid_dates = [
            transaction.date
            for transaction in self.transactions
            if not self.period_start <= transaction.date <= self.period_end
        ]
        if invalid_dates:
            raise ValueError(
                "Transactions fall outside statement period "
                f"{self.period_start} to {self.period_end}: {invalid_dates}"
            )
        LOGGER.info(
            "Validated %d transaction dates within statement period %s to %s",
            len(self.transactions),
            self.period_start,
            self.period_end,
        )

        transaction_total = sum(
            -transaction.amount if transaction.debit else transaction.amount
            for transaction in self.transactions
        )
        calculated_closing_balance = self.opening_balance + transaction_total

        if calculated_closing_balance != self.closing_balance:
            raise ValueError(
                "Statement does not balance: "
                f"opening balance {self.opening_balance} cents + transactions "
                f"{transaction_total} cents = {calculated_closing_balance} cents, "
                f"expected {self.closing_balance} cents"
            )
        LOGGER.info(
            "Validated statement balance in cents: %s + %s = %s",
            self.opening_balance,
            transaction_total,
            self.closing_balance,
        )
