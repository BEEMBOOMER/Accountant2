from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from .models import Transaction


BRISBANE_TIME = timezone(timedelta(hours=10), name="Australia/Brisbane")
WESTPAC_REQUIRED_HEADERS = {
    "Bank Account", "Date", "Narrative", "Debit Amount", "Credit Amount", "Balance"
}


class ImportErrorDetail(ValueError):
    """A row-level validation error that can be shown to the user."""


def detect_bank(text: str) -> str:
    """Identify the supported bank from its CSV shape without using filenames."""
    try:
        rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise ImportErrorDetail(f"CSV could not be read: {exc}") from exc
    if not rows:
        raise ImportErrorDetail("CSV is empty; expected a CommBank or Westpac transaction export")

    if WESTPAC_REQUIRED_HEADERS.issubset({cell.strip() for cell in rows[0]}):
        return "Westpac"

    sample = rows[: min(5, len(rows))]
    if all(len(row) == 4 for row in sample):
        try:
            for row_number, row in enumerate(sample, 1):
                _parse_date(row[0], row_number)
                _parse_decimal(row[1], row_number, "amount")
                _parse_decimal(row[3], row_number, "balance")
        except ImportErrorDetail:
            pass
        else:
            return "CommBank"

    raise ImportErrorDetail(
        "CSV structure is not recognized as a CommBank or Westpac transaction export"
    )


def normalize_description(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().upper()
    return value


def fingerprint(*, bank: str, account: str, transaction_date: date, amount: Decimal,
                normalized_description: str, balance: Decimal | None) -> str:
    balance_text = "" if balance is None else format(balance, "f")
    raw = "|".join((bank.strip().upper(), account.strip(), transaction_date.isoformat(),
                     format(amount, "f"), normalized_description, balance_text))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_date(value: str, row: int) -> date:
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ImportErrorDetail(f"row {row}: invalid date {value!r}")


def _parse_decimal(value: str, row: int, field: str) -> Decimal:
    try:
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            raise InvalidOperation
        parsed = Decimal(cleaned)
        if not parsed.is_finite():
            raise InvalidOperation
        return parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ImportErrorDetail(f"row {row}: invalid {field} {value!r}") from None


def _parse_optional_decimal(value: str, row: int, field: str) -> Decimal | None:
    if not value or not value.strip():
        return None
    return _parse_decimal(value, row, field)


def parse_commbank(text: str, *, account: str, source_file: str,
                   imported_at: datetime | None = None) -> tuple[list[Transaction], list[str]]:
    """Parse the headerless CommBank Date, Amount, Narrative, Balance export."""
    # Excel stores naive datetimes; use local wall-clock import time consistently.
    now = imported_at or datetime.now(BRISBANE_TIME)
    transactions: list[Transaction] = []
    errors: list[str] = []
    for row_no, row in enumerate(csv.reader(io.StringIO(text)), 1):
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) != 4:
            errors.append(f"row {row_no}: expected exactly 4 columns")
            continue
        try:
            tx_date = _parse_date(row[0], row_no)
            amount = _parse_decimal(row[1], row_no, "amount")
            description = row[2]
            balance = _parse_optional_decimal(row[3], row_no, "balance")
            normalized = normalize_description(description)
            fp = fingerprint(bank="CommBank", account=account, transaction_date=tx_date,
                             amount=amount, normalized_description=normalized, balance=balance)
            tx_type = "credit" if amount > 0 else "debit" if amount < 0 else "other"
            transactions.append(Transaction(
                transaction_id=fp[:16], fingerprint=fp, date=tx_date, bank="CommBank",
                account=account, original_description=description, normalized_description=normalized,
                amount=amount, balance=balance, transaction_type=tx_type, category="Miscellaneous",
                source_file=source_file, source_row=row_no, imported_at=now,
            ))
        except ImportErrorDetail as exc:
            errors.append(str(exc))
    return transactions, errors


def parse_westpac(text: str, *, account: str | None = None, source_file: str,
                  imported_at: datetime | None = None) -> tuple[list[Transaction], list[str]]:
    """Parse the Westpac headered export and merge debit/credit into one amount."""
    now = imported_at or datetime.now(BRISBANE_TIME)
    transactions: list[Transaction] = []
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(text))
    required = WESTPAC_REQUIRED_HEADERS
    headers = set(reader.fieldnames or [])
    if not required.issubset(headers):
        return [], [f"missing Westpac columns: {', '.join(sorted(required - headers))}"]
    for row_no, row in enumerate(reader, 2):
        try:
            row_account = (row.get("Bank Account") or "").strip()
            if not row_account:
                raise ImportErrorDetail(f"row {row_no}: missing bank account")
            if account and row_account != account:
                continue
            tx_date = _parse_date(row.get("Date", ""), row_no)
            debit = _parse_optional_decimal(row.get("Debit Amount", ""), row_no, "debit amount")
            credit = _parse_optional_decimal(row.get("Credit Amount", ""), row_no, "credit amount")
            if (debit is None) == (credit is None):
                raise ImportErrorDetail(f"row {row_no}: exactly one of debit amount or credit amount is required")
            if debit is not None and debit < 0:
                raise ImportErrorDetail(f"row {row_no}: debit amount must not be negative")
            if credit is not None and credit < 0:
                raise ImportErrorDetail(f"row {row_no}: credit amount must not be negative")
            amount = -debit if debit is not None else credit
            assert amount is not None
            description = row.get("Narrative", "")
            balance = _parse_optional_decimal(row.get("Balance", ""), row_no, "balance")
            normalized = normalize_description(description)
            fp = fingerprint(bank="Westpac", account=row_account, transaction_date=tx_date,
                             amount=amount, normalized_description=normalized, balance=balance)
            tx_type = "credit" if amount > 0 else "debit" if amount < 0 else "other"
            transactions.append(Transaction(
                transaction_id=fp[:16], fingerprint=fp, date=tx_date, bank="Westpac",
                account=row_account, original_description=description, normalized_description=normalized,
                amount=amount, balance=balance, transaction_type=tx_type, category="Miscellaneous",
                source_file=source_file, source_row=row_no, imported_at=now,
            ))
        except ImportErrorDetail as exc:
            errors.append(str(exc))
    return transactions, errors


def parse_bank(text: str, *, bank: str | None, account: str | None, source_file: str,
               imported_at: datetime | None = None) -> tuple[list[Transaction], list[str]]:
    detected = detect_bank(text)
    if bank and bank.strip() and bank.strip().lower() not in {
        detected.lower(), "commonwealth" if detected == "CommBank" else detected.lower(),
        "commonwealth bank" if detected == "CommBank" else detected.lower(),
        "cba" if detected == "CommBank" else detected.lower(),
    }:
        raise ImportErrorDetail(f"selected bank {bank!r} does not match detected {detected} CSV structure")
    bank = detected
    if bank.lower() in {"commbank", "commonwealth", "cba"}:
        if not account:
            raise ImportErrorDetail("an account is required for a CommBank import")
        return parse_commbank(text, account=account, source_file=source_file, imported_at=imported_at)
    if bank.lower() == "westpac":
        return parse_westpac(text, account=account, source_file=source_file, imported_at=imported_at)
    raise ImportErrorDetail(f"unsupported bank {bank!r}")
