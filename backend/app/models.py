from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TransferStatus = Literal["none", "suspected", "confirmed", "rejected"]


class Transaction(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    fingerprint: str
    date: date
    bank: str
    account: str
    original_description: str
    normalized_description: str
    amount: Decimal
    balance: Decimal | None = None
    transaction_type: str
    category: str
    category_manual: bool = False
    transfer_status: TransferStatus = "none"
    internal_transfer: bool = False
    transfer_group_id: str | None = None
    savings_transfer: bool = False
    # These fields are deliberately persisted.  Automatic recognition may be
    # rerun after an import, while a user's financial decision must not change.
    classification: str | None = None
    classification_manual: bool = False
    investment_transfer: bool = False
    expense_reimbursement: bool = False
    review_required: bool = False
    source_file: str = ""
    source_row: int = 0
    imported_at: datetime


class Account(BaseModel):
    id: str
    bank: str
    name: str
    identifier: str
    is_savings: bool = False
    currency: str = "AUD"


class Category(BaseModel):
    id: str
    name: str
    enabled: bool = True


class Rule(BaseModel):
    id: str
    match_type: Literal["exact", "keyword"]
    pattern: str
    category: str
    enabled: bool = True


class ImportHistory(BaseModel):
    id: str
    bank: str
    account: str
    source_file: str
    imported_at: datetime
    processed: int
    inserted: int
    duplicates: int
    suspected_transfers: int
    review_required: int
    rejected: int
    errors: list[str] = Field(default_factory=list)


class MonthlySummary(BaseModel):
    month: str
    income: Decimal
    expenditure: Decimal
    net_cashflow: Decimal
    savings: Decimal
    investments: Decimal = Decimal("0")
    category_totals: dict[str, Decimal] = Field(default_factory=dict)


class AccountCreate(BaseModel):
    bank: str
    name: str
    identifier: str
    is_savings: bool = False
    currency: str = "AUD"


class CategoryCreate(BaseModel):
    name: str


class RuleCreate(BaseModel):
    match_type: Literal["exact", "keyword"]
    pattern: str
    category: str
    enabled: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None


class RuleUpdate(BaseModel):
    match_type: Literal["exact", "keyword"] | None = None
    pattern: str | None = None
    category: str | None = None
    enabled: bool | None = None


class ImportResult(BaseModel):
    bank: str
    account: str
    source_file: str
    processed: int
    inserted: int
    duplicates: int
    suspected_transfers: int
    transfers: int = 0
    review_required: int
    rejected: int
    errors: list[str] = Field(default_factory=list)
    latest_month: str | None = None
