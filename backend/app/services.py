from __future__ import annotations

import re
import threading
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from .category_lookup import CURATED_CATEGORIES, CURATED_RULES
from .importers import BRISBANE_TIME, detect_bank, normalize_description, parse_bank
from .models import Account, Category, ImportHistory, ImportResult, MonthlySummary, Rule, Transaction
from .workbook import WorkbookStore


TRANSFER_RE = re.compile(r"\b(?:TRANSFER|TFR|XX\d{3,}|DEPOSIT ONLINE|DEPOSIT-OSKO)\b", re.I)
OWNER_TRANSFER_NAMES = ("ANAY VENUGOPAL",)
REIMBURSEMENT_KEYWORDS = ("WIFI", "IINET")
WEBULL_PAYTO_RE = re.compile(r"\bPAYTO\s+WEBULL\s+SECURITIES\b", re.I)
SAVINGS_DESTINATION_RE = re.compile(r"\bTRANSFER\s+TO\s+(?:WESTPAC|COMMBANK|XX\d{3,}).*\bSAVINGS\b", re.I)
OWN_DAILY_DESTINATION_RE = re.compile(r"\bTRANSFER\s+TO\s+DAILY\s+ANAY\s+COMMBANK\s+APP\b", re.I)
OWN_XX_DESTINATION_RE = re.compile(r"\bTRANSFER\s+(?:TO|FROM)\s+XX\d{3,}\s+COMMBANK\s+APP\b", re.I)
TARGET_BANK_RE = re.compile(r"\b(?:TRANSFER|TFR)\s+(?:TO|FROM)\s+(WESTPAC|COMMBANK)\b", re.I)


class NotFoundError(KeyError):
    pass


class ValidationError(ValueError):
    pass


def synchronized(method):
    """Hold the service lock across each complete read-modify-write operation."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._mutation_lock:
            return method(self, *args, **kwargs)
    return wrapped


class BankingService:
    def __init__(self, store: WorkbookStore | None = None):
        self._mutation_lock = threading.RLock()
        self.store = store or WorkbookStore()

    def state(self):
        return self.store.read_all()

    @synchronized
    def upgrade_classification_schema(self) -> dict[str, int | bool]:
        """Explicit one-time upgrade that preserves legacy transfer decisions.

        Call this only after making a filesystem backup of the workbook.  The
        initial read marks pre-schema confirmed groups/rejections as manual;
        the following atomic write records those decisions with the new fields.
        """
        txs, categories, rules, accounts, history, _ = self.state()
        changed = not self.store.has_classification_schema()
        protected = sum(tx.classification_manual for tx in txs)
        if changed:
            self.persist(txs, categories, rules, accounts, history, recompute=False)
        return {"schema_changed": changed, "legacy_decisions_preserved": protected}

    @staticmethod
    def _bank_key(value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"commbank", "commonwealth", "commonwealth bank", "cba"}:
            return "commbank"
        if normalized == "westpac":
            return "westpac"
        return normalized

    @staticmethod
    def _category_name(categories, category: str) -> str:
        names = {c.name for c in categories}
        return category if category in names else ("Miscellaneous" if "Miscellaneous" in names else (categories[0].name if categories else "Miscellaneous"))

    @staticmethod
    def _keyword_matches(pattern: str, description: str) -> bool:
        """Match a keyword as a phrase bounded by non-alphanumeric characters."""
        normalized_pattern = normalize_description(pattern)
        if not normalized_pattern:
            return False
        expression = rf"(?<![A-Z0-9]){re.escape(normalized_pattern)}(?![A-Z0-9])"
        return re.search(expression, description) is not None

    def categorize(self, tx: Transaction, categories: list[Category], rules: list[Rule]) -> tuple[str, bool]:
        description = tx.normalized_description
        tx.expense_reimbursement = self._is_expense_reimbursement(tx)
        enabled = [r for r in rules if r.enabled]
        for rule in enabled:
            if rule.match_type == "exact" and normalize_description(rule.pattern) == description:
                return self._category_name(categories, rule.category), False
        # These are transaction-direction-specific financial cases.  They are
        # intentionally before generic merchant keywords (for example QUT is
        # both an education keyword and an employer); exact user rules above
        # still take precedence.
        automatic = self._automatic_category(tx)
        if automatic:
            return self._category_name(categories, automatic), False
        for rule in enabled:
            if rule.match_type == "keyword" and self._keyword_matches(rule.pattern, description):
                return self._category_name(categories, rule.category), False
        return self._category_name(categories, "Miscellaneous"), True

    def _automatic_category(self, tx: Transaction) -> str | None:
        if tx.amount > 0 and self._keyword_matches("QUT", tx.normalized_description):
            return "Income"
        if self._is_expense_reimbursement(tx):
            return "Phone & Subscriptions"
        return None

    def _is_expense_reimbursement(self, tx: Transaction) -> bool:
        return tx.amount > 0 and any(
            self._keyword_matches(keyword, tx.normalized_description)
            for keyword in REIMBURSEMENT_KEYWORDS
        )

    def _has_exact_rule(self, tx: Transaction, rules: list[Rule]) -> bool:
        return any(
            rule.enabled
            and rule.match_type == "exact"
            and normalize_description(rule.pattern) == tx.normalized_description
            for rule in rules
        )

    @synchronized
    def install_curated_lookup(self) -> dict[str, int]:
        """Install the curated lookup and classify unresolved workbook rows.

        Existing categories and rule choices take priority. Only transactions that
        are still pending in Miscellaneous are eligible for migration.
        """
        txs, categories, rules, accounts, history, _ = self.state()
        existing_categories = {category.name.casefold() for category in categories}
        categories_added = 0
        for name in CURATED_CATEGORIES:
            if name.casefold() not in existing_categories:
                categories.append(Category(id=str(uuid.uuid4()), name=name, enabled=True))
                existing_categories.add(name.casefold())
                categories_added += 1

        existing_rules = {
            (rule.match_type, normalize_description(rule.pattern))
            for rule in rules
        }
        rules_added = 0
        for match_type, pattern, category in CURATED_RULES:
            key = (match_type, normalize_description(pattern))
            if key in existing_rules:
                continue
            rules.append(Rule(
                id=str(uuid.uuid4()),
                match_type=match_type,
                pattern=pattern,
                category=category,
                enabled=True,
            ))
            existing_rules.add(key)
            rules_added += 1

        recategorized = 0
        for tx in txs:
            if tx.category != "Miscellaneous" or not tx.review_required or tx.category_manual:
                continue
            category, still_unresolved = self.categorize(tx, categories, rules)
            if still_unresolved:
                continue
            tx.category = category
            tx.review_required = tx.transfer_status == "suspected"
            recategorized += 1

        if categories_added or rules_added or recategorized:
            self.persist(txs, categories, rules, accounts, history, recompute=False)
        return {
            "categories_added": categories_added,
            "rules_added": rules_added,
            "transactions_recategorized": recategorized,
        }

    @staticmethod
    def _is_transfer_candidate(tx: Transaction, accounts: list[Account]) -> bool:
        if tx.amount == 0:
            return False
        if TRANSFER_RE.search(tx.original_description):
            return True
        return any(a.identifier and a.identifier.lower() in tx.original_description.lower() for a in accounts)

    def _is_owner_transfer_deposit(self, tx: Transaction, accounts: list[Account]) -> bool:
        if tx.amount <= 0 or not self._is_transfer_candidate(tx, accounts):
            return False
        if tx.account not in {key for account in accounts for key in (account.id, account.identifier)}:
            return False
        return any(self._keyword_matches(name, tx.normalized_description) for name in OWNER_TRANSFER_NAMES)

    def _confirm_transfer(self, tx: Transaction, savings_keys: set[str], group: str | None = None) -> None:
        if tx.classification_manual:
            return
        tx.transfer_status = "confirmed"
        tx.internal_transfer = True
        tx.transfer_group_id = group or tx.transfer_group_id or f"automatic:{tx.fingerprint}"
        tx.savings_transfer = tx.amount > 0 and (
            tx.account in savings_keys
            or self._keyword_matches("SAVINGS ACCOUNT", tx.normalized_description)
        )
        tx.review_required = False

    @staticmethod
    def _is_webull_investment(tx: Transaction) -> bool:
        return tx.amount < 0 and WEBULL_PAYTO_RE.search(tx.original_description) is not None

    @staticmethod
    def _is_standalone_savings_destination(tx: Transaction) -> bool:
        return tx.amount < 0 and SAVINGS_DESTINATION_RE.search(tx.original_description) is not None

    @staticmethod
    def _is_known_own_outbound(tx: Transaction) -> bool:
        # Masked CommBank own-account transfers appear in both directions.
        # The named Daily destination is only established for outgoing rows.
        return ((tx.amount < 0 and OWN_DAILY_DESTINATION_RE.search(tx.original_description) is not None)
                or OWN_XX_DESTINATION_RE.search(tx.original_description) is not None)

    def _pair_is_compatible(self, left: Transaction, right: Transaction, accounts: list[Account]) -> bool:
        """Reject equal-value pairs whose stated destination is another bank.

        Amount/date alone is insufficient: an xx2990 CommBank transfer cannot
        be paired with a Westpac deposit just because it happens nearby.
        """
        for source, counterpart in ((left, right), (right, left)):
            description = source.normalized_description
            target = TARGET_BANK_RE.search(description)
            expected_bank = self._bank_key(target.group(1)) if target else None
            if expected_bank and self._bank_key(counterpart.bank) != expected_bank:
                return False
            mentioned_accounts = [a.identifier for a in accounts if a.identifier and a.identifier.upper() in description]
            if mentioned_accounts and counterpart.account not in mentioned_accounts:
                return False
        return True

    def classification(self, tx: Transaction) -> str:
        """Return the sole cashflow membership used by summaries and drilldowns."""
        if tx.classification_manual and tx.classification:
            return tx.classification
        if tx.transfer_status == "rejected":
            return "reimbursement" if tx.expense_reimbursement else ("income" if tx.amount > 0 else "expense")
        if self._is_webull_investment(tx) or tx.investment_transfer:
            return "investment"
        if tx.transfer_status == "confirmed" and tx.savings_transfer:
            return "savings"
        if self._is_standalone_savings_destination(tx):
            return "savings"
        if tx.transfer_status == "confirmed":
            return "transfer"
        if tx.expense_reimbursement:
            return "reimbursement"
        return "income" if tx.amount > 0 else "expense"

    def detect_transfers(self, transactions: list[Transaction], accounts: list[Account]) -> int:
        # Recompute only automatic statuses; manual decisions are durable.  By
        # reopening automatic matches, a counterpart imported later can form a
        # single paired transfer group.
        legacy_schema = not self.store.has_classification_schema()
        for tx in transactions:
            if tx.transfer_status == "suspected" or (tx.transfer_status == "confirmed" and not tx.classification_manual and not (legacy_schema and tx.transfer_group_id and not str(tx.transfer_group_id).startswith("automatic:"))):
                tx.transfer_status = "none"
                tx.internal_transfer = False
                tx.transfer_group_id = None
                tx.savings_transfer = False
                tx.review_required = tx.category == "Miscellaneous"
        # Account values may be either configured IDs or bank identifiers in imported rows.
        savings_keys = {a.id for a in accounts if a.is_savings} | {a.identifier for a in accounts if a.is_savings}
        for tx in transactions:
            if tx.transfer_status == "confirmed":
                self._confirm_transfer(tx, savings_keys)
        pair_count = 0
        ordered = sorted(transactions, key=lambda t: (t.date, t.transaction_id))
        used: set[str] = set()
        for idx, left in enumerate(ordered):
            if left.transaction_id in used or left.transfer_status in {"confirmed", "rejected"}:
                continue
            if not self._is_transfer_candidate(left, accounts):
                continue
            best: Transaction | None = None
            for right in ordered[idx + 1:]:
                if right.transaction_id in used or right.transfer_status in {"confirmed", "rejected"}:
                    continue
                if left.account == right.account or left.amount != -right.amount:
                    continue
                if abs((right.date - left.date).days) > 3:
                    if right.date > left.date + timedelta(days=3):
                        break
                    continue
                if not self._is_transfer_candidate(right, accounts):
                    continue
                if not self._pair_is_compatible(left, right, accounts):
                    continue
                if best is None or abs((right.date - left.date).days) < abs((best.date - left.date).days):
                    best = right
            if best is not None:
                group = str(uuid.uuid4())
                auto_confirm = self._is_owner_transfer_deposit(left, accounts) or self._is_owner_transfer_deposit(best, accounts)
                for tx in (left, best):
                    if auto_confirm:
                        self._confirm_transfer(tx, savings_keys, group)
                    else:
                        tx.transfer_status = "suspected"
                        # A suspected match remains ordinary cash flow until the user confirms it.
                        tx.internal_transfer = False
                        tx.transfer_group_id = group
                        tx.review_required = True
                        tx.savings_transfer = False
                used.update((left.transaction_id, best.transaction_id))
                pair_count += 1
        for tx in transactions:
            if tx.transfer_status == "none" and (self._is_owner_transfer_deposit(tx, accounts) or self._is_known_own_outbound(tx)):
                self._confirm_transfer(tx, savings_keys)
        # Persist automatic decisions for workbook inspection.  The manual flag
        # remains the authority over future detection/re-import work.
        for tx in transactions:
            if tx.classification_manual:
                continue
            tx.investment_transfer = self._is_webull_investment(tx)
            if tx.investment_transfer:
                tx.review_required = False
            if self._is_standalone_savings_destination(tx):
                # The description identifies an own savings destination even
                # if only the outgoing statement has been imported.
                tx.transfer_status = "confirmed"
                tx.internal_transfer = True
                tx.savings_transfer = True
                tx.review_required = False
            tx.classification = self.classification(tx)
        return pair_count

    def summaries(self, transactions: list[Transaction]) -> list[MonthlySummary]:
        grouped: dict[str, list[Transaction]] = defaultdict(list)
        for tx in transactions:
            grouped[tx.date.strftime("%Y-%m")].append(tx)
        metric_representatives = {
            tx.transaction_id for tx in self._metric_representatives(transactions, {"savings", "investment"})
        }
        result: list[MonthlySummary] = []
        for month in sorted(grouped):
            income = Decimal("0")
            expenditure = Decimal("0")
            savings = Decimal("0")
            investments = Decimal("0")
            categories: dict[str, Decimal] = defaultdict(Decimal)
            for tx in grouped[month]:
                kind = self.classification(tx)
                # A transfer group is represented by its inbound savings leg;
                # when only the outgoing statement was imported, that leg is
                # the safe fallback.  Never count both.
                group_key = tx.transfer_group_id or tx.transaction_id
                if kind in {"savings", "investment"}:
                    if tx.transaction_id not in metric_representatives:
                        continue
                    if kind == "savings": savings += abs(tx.amount)
                    else: investments += abs(tx.amount)
                    continue
                if kind not in {"transfer", "savings", "investment"}:
                    if kind == "reimbursement":
                        expenditure -= tx.amount
                    elif kind == "income":
                        income += tx.amount
                    elif kind == "expense":
                        expenditure += abs(tx.amount)
                if kind == "expense":
                    categories[tx.category] += abs(tx.amount)
                elif kind == "reimbursement":
                    categories[tx.category] -= tx.amount
            result.append(MonthlySummary(month=month, income=income, expenditure=expenditure,
                                         net_cashflow=income - expenditure, savings=savings,
                                         investments=investments, category_totals=dict(categories)))
        return result

    def _metric_representatives(self, txs: list[Transaction], kinds: set[str]) -> list[Transaction]:
        """Choose a single metric row per group, preferring the destination credit."""
        grouped: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
        for tx in txs:
            kind = self.classification(tx)
            if kind in kinds:
                grouped[(kind, tx.transfer_group_id or tx.transaction_id)].append(tx)
        result = []
        for items in grouped.values():
            result.append(sorted(items, key=lambda tx: (tx.amount > 0, tx.date, tx.transaction_id), reverse=True)[0])
        return result

    @synchronized
    def apply_financial_patterns(self) -> dict[str, int]:
        """Apply high-confidence cashflow patterns to existing workbook rows."""
        txs, categories, rules, accounts, history, _ = self.state()
        recategorized = 0
        reimbursements = 0
        before_confirmed = {tx.transaction_id for tx in txs if tx.transfer_status == "confirmed"}
        for tx in txs:
            was_reimbursement = tx.expense_reimbursement
            if not tx.classification_manual:
                tx.expense_reimbursement = self._is_expense_reimbursement(tx)
            if tx.expense_reimbursement and not was_reimbursement:
                reimbursements += 1
            automatic = self._automatic_category(tx)
            if automatic and not tx.category_manual and not self._has_exact_rule(tx, rules) and tx.category != automatic:
                tx.category = self._category_name(categories, automatic)
                tx.review_required = tx.transfer_status == "suspected"
                recategorized += 1
        self.detect_transfers(txs, accounts)
        transfers_confirmed = sum(
            tx.transfer_status == "confirmed" and tx.transaction_id not in before_confirmed
            for tx in txs
        )
        self.persist(txs, categories, rules, accounts, history, recompute=False)
        return {
            "transactions_recategorized": recategorized,
            "reimbursements_identified": reimbursements,
            "transfer_rows_confirmed": transfers_confirmed,
        }

    def persist(self, transactions, categories, rules, accounts, history, *, recompute=True):
        if recompute:
            self.detect_transfers(transactions, accounts)
        summaries = self.summaries(transactions)
        self.store.replace_all(transactions, categories, rules, accounts, history, summaries)

    @staticmethod
    def _parser_account(bank: str, account: str | None, accounts: list[Account]) -> str | None:
        normalized_bank = BankingService._bank_key(bank)
        if normalized_bank not in {"commbank", "westpac"}:
            raise ValidationError(f"unsupported bank {bank!r}")
        if normalized_bank == "commbank" and not account:
            raise ValidationError("select a configured CommBank account")
        if account:
            configured = next(
                (a for a in accounts if account in {a.id, a.identifier} and BankingService._bank_key(a.bank) == normalized_bank),
                None,
            )
            if not configured:
                raise ValidationError("the selected account is not configured for this bank")
            return configured.identifier
        return None

    @synchronized
    def import_csv(self, text: str, *, bank: str | None = None, account: str | None, source_file: str) -> ImportResult:
        all_txs, categories, rules, accounts, history, _ = self.state()
        detected_bank = detect_bank(text)
        if bank and self._bank_key(bank) != self._bank_key(detected_bank):
            raise ValidationError(f"selected bank {bank!r} does not match detected {detected_bank} CSV structure")
        bank = detected_bank
        parser_account = self._parser_account(bank, account, accounts)
        transactions, errors = parse_bank(text, bank=bank, account=parser_account, source_file=source_file)
        configured_keys = {key for a in accounts for key in (a.id, a.identifier)}
        unknown_accounts = sorted({tx.account for tx in transactions if tx.account not in configured_keys})
        if unknown_accounts:
            raise ValidationError(f"configure these statement accounts before importing: {', '.join(unknown_accounts)}")
        account_value = account or "multiple"
        existing = {tx.fingerprint for tx in all_txs}
        inserted = 0
        duplicates = 0
        inserted_transactions: list[Transaction] = []
        for tx in transactions:
            if tx.fingerprint in existing:
                duplicates += 1
                continue
            tx.category, tx.review_required = self.categorize(tx, categories, rules)
            all_txs.append(tx)
            inserted_transactions.append(tx)
            existing.add(tx.fingerprint)
            inserted += 1
        self.detect_transfers(all_txs, accounts)
        suspected = sum(1 for tx in inserted_transactions if tx.transfer_status == "suspected")
        transfer_groups = {
            tx.transfer_group_id
            for tx in inserted_transactions
            if tx.transfer_status in {"suspected", "confirmed"} and tx.transfer_group_id
        }
        review = sum(1 for tx in inserted_transactions if tx.review_required)
        result = ImportResult(bank=bank, account=account_value, source_file=source_file,
                              processed=len(transactions) + len(errors), inserted=inserted,
                              duplicates=duplicates, suspected_transfers=suspected,
                              transfers=len(transfer_groups),
                              review_required=review, rejected=len(errors), errors=errors,
                              latest_month=max((tx.date for tx in transactions), default=None).strftime("%Y-%m")
                              if transactions else None)
        history.append(ImportHistory(id=str(uuid.uuid4()), bank=bank, account=account_value,
                                     source_file=source_file, imported_at=datetime.now(BRISBANE_TIME),
                                     processed=result.processed, inserted=inserted, duplicates=duplicates,
                                     suspected_transfers=suspected, review_required=review,
                                     rejected=len(errors), errors=errors))
        self.persist(all_txs, categories, rules, accounts, history, recompute=False)
        return result

    def preview_csv(self, text: str, *, bank: str | None = None, account: str | None, source_file: str):
        existing_txs, categories, rules, accounts, _, _ = self.state()
        detected_bank = detect_bank(text)
        if bank and self._bank_key(bank) != self._bank_key(detected_bank):
            raise ValidationError(f"selected bank {bank!r} does not match detected {detected_bank} CSV structure")
        bank = detected_bank
        parser_account = self._parser_account(bank, account, accounts)
        txs, errors = parse_bank(text, bank=bank, account=parser_account, source_file=source_file)
        configured_keys = {key for a in accounts for key in (a.id, a.identifier)}
        unknown_accounts = sorted({tx.account for tx in txs if tx.account not in configured_keys})
        if unknown_accounts:
            raise ValidationError(f"configure these statement accounts before importing: {', '.join(unknown_accounts)}")
        existing = {tx.fingerprint for tx in existing_txs}
        suggested = [self.categorize(tx, categories, rules)[0] for tx in txs]
        duplicates = 0
        new_transactions: list[Transaction] = []
        seen = set(existing)
        for tx, category in zip(txs, suggested):
            if tx.fingerprint in seen:
                duplicates += 1
                continue
            seen.add(tx.fingerprint)
            tx.category = category
            tx.review_required = category == "Miscellaneous"
            new_transactions.append(tx)
        self.detect_transfers(existing_txs + new_transactions, accounts)
        suspected = sum(tx.transfer_status == "suspected" for tx in new_transactions)
        groups = len({tx.transfer_group_id for tx in new_transactions if tx.transfer_group_id})
        review = sum(tx.review_required for tx in new_transactions)
        return txs, errors, suggested, duplicates, suspected, groups, review

    @synchronized
    def create_account(self, data: dict) -> Account:
        txs, categories, rules, accounts, history, _ = self.state()
        data = dict(data)
        for field in ("bank", "name", "identifier"):
            data[field] = str(data.get(field, "")).strip()
            if not data[field]:
                raise ValidationError(f"{field} is required")
        if self._bank_key(data["bank"]) not in {"commbank", "westpac"}:
            raise ValidationError("bank must be CommBank or Westpac")
        data["currency"] = str(data.get("currency", "AUD")).upper()
        if data["currency"] != "AUD":
            raise ValidationError("only AUD accounts are supported")
        if any(a.identifier == data["identifier"] and self._bank_key(a.bank) == self._bank_key(data["bank"]) for a in accounts):
            raise ValidationError("an account with this bank identifier already exists")
        account = Account(id=str(uuid.uuid4()), **data)
        accounts.append(account)
        self.persist(txs, categories, rules, accounts, history, recompute=False)
        return account

    @synchronized
    def update_account(self, account_id: str, data: dict) -> Account:
        txs, categories, rules, accounts, history, _ = self.state()
        account = next((a for a in accounts if a.id == account_id), None)
        if not account: raise NotFoundError("account")
        data = dict(data)
        for field in ("bank", "name", "identifier"):
            if field in data and data[field] is not None:
                data[field] = str(data[field]).strip()
                if not data[field]: raise ValidationError(f"{field} is required")
        if "currency" in data and data["currency"] is not None:
            data["currency"] = str(data["currency"]).upper()
            if data["currency"] != "AUD": raise ValidationError("only AUD accounts are supported")
        next_bank = self._bank_key(str(data.get("bank", account.bank)))
        if next_bank not in {"commbank", "westpac"}:
            raise ValidationError("bank must be CommBank or Westpac")
        next_identifier = str(data.get("identifier", account.identifier))
        account_is_referenced = any(tx.account in {account.id, account.identifier} for tx in txs)
        if account_is_referenced and (
            next_bank != self._bank_key(account.bank) or next_identifier != account.identifier
        ):
            raise ValidationError("bank and identifier cannot be changed after transactions have been imported")
        if any(a.id != account_id and self._bank_key(a.bank) == next_bank and a.identifier == next_identifier for a in accounts):
            raise ValidationError("an account with this bank identifier already exists")
        for key, value in data.items():
            if value is not None and hasattr(account, key): setattr(account, key, value)
        self.persist(txs, categories, rules, accounts, history)
        return account

    @synchronized
    def delete_account(self, account_id: str) -> None:
        txs, categories, rules, accounts, history, _ = self.state()
        if not any(a.id == account_id for a in accounts): raise NotFoundError("account")
        if any(tx.account == account_id or tx.account == next((a.identifier for a in accounts if a.id == account_id), "") for tx in txs):
            raise ValidationError("cannot delete an account that has transactions")
        accounts = [a for a in accounts if a.id != account_id]
        self.persist(txs, categories, rules, accounts, history, recompute=False)

    @synchronized
    def create_category(self, name: str) -> Category:
        txs, categories, rules, accounts, history, _ = self.state()
        if not name or not name.strip(): raise ValidationError("category name is required")
        name = name.strip()
        if any(c.name.lower() == name.lower() for c in categories): raise ValidationError("category already exists")
        category = Category(id=str(uuid.uuid4()), name=name.strip())
        categories.append(category); self.persist(txs, categories, rules, accounts, history, recompute=False); return category

    @synchronized
    def update_category(self, category_id: str, data: dict) -> Category:
        txs, categories, rules, accounts, history, _ = self.state()
        category = next((c for c in categories if c.id == category_id), None)
        if not category: raise NotFoundError("category")
        old = category.name
        if old == "Miscellaneous" and data.get("name") not in {None, old}:
            raise ValidationError("Miscellaneous is the required manual-review category and cannot be renamed")
        data = dict(data)
        if "name" in data and data["name"] is not None:
            data["name"] = str(data["name"]).strip()
            if not data["name"]: raise ValidationError("category name is required")
            if any(c.id != category_id and c.name.lower() == data["name"].lower() for c in categories):
                raise ValidationError("category already exists")
        for key, value in data.items():
            if value is not None and hasattr(category, key): setattr(category, key, value)
        if category.name != old:
            for tx in txs:
                if tx.category == old: tx.category = category.name
            for rule in rules:
                if rule.category == old: rule.category = category.name
        self.persist(txs, categories, rules, accounts, history, recompute=False); return category

    @synchronized
    def delete_category(self, category_id: str, replacement_category_id: str | None) -> None:
        txs, categories, rules, accounts, history, _ = self.state()
        category = next((c for c in categories if c.id == category_id), None)
        if not category: raise NotFoundError("category")
        if category.name == "Miscellaneous":
            raise ValidationError("Miscellaneous is the required manual-review category and cannot be removed")
        used = any(tx.category == category.name for tx in txs) or any(r.category == category.name for r in rules)
        replacement = next((c for c in categories if c.id == replacement_category_id), None) if replacement_category_id else None
        if used and (not replacement or replacement.id == category_id):
            raise ValidationError("replacement_category_id is required for a category in use")
        if replacement:
            for tx in txs:
                if tx.category == category.name: tx.category = replacement.name
            for rule in rules:
                if rule.category == category.name: rule.category = replacement.name
        categories = [c for c in categories if c.id != category_id]
        self.persist(txs, categories, rules, accounts, history, recompute=False)

    @synchronized
    def create_rule(self, data: dict) -> Rule:
        txs, categories, rules, accounts, history, _ = self.state()
        data = dict(data)
        data["pattern"] = str(data.get("pattern", "")).strip()
        if not data["pattern"]: raise ValidationError("rule pattern is required")
        if not any(c.name == data["category"] for c in categories): raise ValidationError("unknown category")
        rule = Rule(id=str(uuid.uuid4()), **data); rules.append(rule); self.persist(txs, categories, rules, accounts, history, recompute=False); return rule

    @synchronized
    def update_rule(self, rule_id: str, data: dict) -> Rule:
        txs, categories, rules, accounts, history, _ = self.state()
        rule = next((r for r in rules if r.id == rule_id), None)
        if not rule: raise NotFoundError("rule")
        data = dict(data)
        if "pattern" in data and data["pattern"] is not None:
            data["pattern"] = str(data["pattern"]).strip()
            if not data["pattern"]: raise ValidationError("rule pattern is required")
        for key, value in data.items():
            if value is not None and hasattr(rule, key): setattr(rule, key, value)
        if not any(c.name == rule.category for c in categories): raise ValidationError("unknown category")
        self.persist(txs, categories, rules, accounts, history, recompute=False); return rule

    @synchronized
    def delete_rule(self, rule_id: str) -> None:
        txs, categories, rules, accounts, history, _ = self.state()
        if not any(r.id == rule_id for r in rules): raise NotFoundError("rule")
        self.persist(txs, categories, [r for r in rules if r.id != rule_id], accounts, history, recompute=False)

    @synchronized
    def set_category(self, tx_id: str, category: str, create_rule: bool = False) -> Transaction:
        txs, categories, rules, accounts, history, _ = self.state()
        tx = next((t for t in txs if t.transaction_id == tx_id or t.fingerprint == tx_id), None)
        if not tx: raise NotFoundError("transaction")
        if category not in {c.name for c in categories}: raise ValidationError("unknown category")
        tx.category = category
        tx.category_manual = True
        # Categorising a suspected transfer resolves its category, not the transfer decision.
        tx.review_required = tx.transfer_status == "suspected"
        if create_rule:
            existing_rule = next((r for r in rules if r.match_type == "exact" and normalize_description(r.pattern) == tx.normalized_description), None)
            if existing_rule:
                existing_rule.category = category
                existing_rule.enabled = True
            else:
                rules.append(Rule(id=str(uuid.uuid4()), match_type="exact", pattern=tx.normalized_description, category=category, enabled=True))
        self.persist(txs, categories, rules, accounts, history, recompute=False); return tx

    @synchronized
    def set_transfer(self, tx_id: str, status: str) -> Transaction:
        if status not in {"confirmed", "rejected"}: raise ValidationError("status must be confirmed or rejected")
        txs, categories, rules, accounts, history, _ = self.state()
        tx = next((t for t in txs if t.transaction_id == tx_id or t.fingerprint == tx_id), None)
        if not tx: raise NotFoundError("transaction")
        group = tx.transfer_group_id
        related = [t for t in txs if group and t.transfer_group_id == group] if group else [tx]
        for item in related:
            item.transfer_status = status
            item.internal_transfer = status == "confirmed"
            item.review_required = False
            item.savings_transfer = status == "confirmed" and (
                (item.amount > 0 and any(item.account in {a.id, a.identifier} and a.is_savings for a in accounts))
                or self._is_standalone_savings_destination(item)
            )
            if status == "confirmed":
                item.classification = "savings" if item.savings_transfer else "transfer"
            else:
                item.classification = "reimbursement" if item.expense_reimbursement else ("income" if item.amount > 0 else "expense")
            item.classification_manual = True
        self.persist(txs, categories, rules, accounts, history, recompute=False); return tx

    @synchronized
    def set_classification(self, tx_id: str, classification: str, category: str | None = None) -> Transaction:
        if classification not in {"expense", "income", "transfer", "savings", "investment", "reimbursement"}:
            raise ValidationError("classification must be expense, income, transfer, savings, investment, or reimbursement")
        txs, categories, rules, accounts, history, _ = self.state()
        tx = next((t for t in txs if t.transaction_id == tx_id or t.fingerprint == tx_id), None)
        if not tx: raise NotFoundError("transaction")
        if classification in {"expense", "investment"} and tx.amount >= 0:
            raise ValidationError(f"{classification} classification requires an outgoing transaction")
        if classification in {"income", "reimbursement"} and tx.amount <= 0:
            raise ValidationError(f"{classification} classification requires an incoming transaction")
        if category is not None:
            if category not in {c.name for c in categories}: raise ValidationError("unknown category")
            tx.category = category; tx.category_manual = True
        related = [item for item in txs if tx.transfer_group_id and item.transfer_group_id == tx.transfer_group_id]
        if classification in {"transfer", "savings", "investment"}:
            # Financial transfer decisions apply to the whole matched pair.
            for item in related or [tx]:
                paired_savings = classification == "savings" and len(related) > 1
                item.classification = classification if classification != "savings" or not paired_savings or item.amount > 0 else "transfer"
                item.classification_manual = True
                item.investment_transfer = classification == "investment"
                item.internal_transfer = True
                item.transfer_status = "confirmed"
                item.savings_transfer = classification == "savings" and (not paired_savings or item.amount > 0)
                item.expense_reimbursement = False
                item.review_required = False
        else:
            # An ordinary cashflow correction breaks the transfer relationship
            # on every leg, leaving no stale savings/investment membership.
            for item in related or [tx]:
                item.transfer_group_id = None
                item.classification = "reimbursement" if item.expense_reimbursement else ("income" if item.amount > 0 else "expense")
                item.classification_manual = True
                item.investment_transfer = False
                item.internal_transfer = False
                item.transfer_status = "rejected"
                item.savings_transfer = False
                item.review_required = False
            tx.classification = classification
            tx.expense_reimbursement = classification == "reimbursement"
        self.persist(txs, categories, rules, accounts, history, recompute=False)
        return tx

    def analytics(self, month: str | None = None) -> dict:
        txs, _, _, _, _, _ = self.state()
        summary = self.summaries(txs)
        current = next((item for item in summary if item.month == month), None) if month else (summary[-1] if summary else None)
        current = current or MonthlySummary(month=month or "", income=Decimal("0"), expenditure=Decimal("0"), net_cashflow=Decimal("0"), savings=Decimal("0"))
        scoped = [t for t in txs if not month or t.date.strftime("%Y-%m") == month]
        category = sorted(current.category_totals.items(), key=lambda x: (-x[1], x[0]))
        expenses = sorted((t for t in scoped if self.classification(t) == "expense" and t.amount < 0), key=lambda t: (-abs(t.amount), t.original_description))
        return {"month": current.month, "income": current.income, "expenditure": current.expenditure, "net_cashflow": current.net_cashflow, "savings": current.savings, "investments": current.investments, "spending_by_category": [{"category": k, "amount": v} for k, v in category], "top_categories": [{"category": k, "amount": v} for k, v in category[:3]], "top_expenses": [{"description": t.original_description, "amount": abs(t.amount), "date": t.date.isoformat(), "category": t.category} for t in expenses[:3]]}

    def metric_transactions(self, metric: str, month: str | None = None) -> list[Transaction]:
        if metric not in {"income", "expenditure", "savings", "investments"}:
            raise ValidationError("metric must be income, expenditure, savings, or investments")
        txs = self.state()[0]
        wanted = {"income": {"income"}, "expenditure": {"expense", "reimbursement"}, "savings": {"savings"}, "investments": {"investment"}}[metric]
        if metric in {"savings", "investments"}:
            result = self._metric_representatives(txs, wanted)
        else:
            result = [tx for tx in txs if self.classification(tx) in wanted]
        return [tx for tx in result if not month or tx.date.strftime("%Y-%m") == month]

    def available_months(self) -> list[str]:
        txs, _, _, _, _, _ = self.state()
        return sorted({tx.date.strftime("%Y-%m") for tx in txs}, reverse=True)
