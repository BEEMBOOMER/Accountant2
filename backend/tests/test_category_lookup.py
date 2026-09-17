from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from backend.app.models import Category, Transaction
from backend.app.services import BankingService
from backend.app.workbook import WorkbookStore


ROOT = Path(__file__).resolve().parents[2]


def service(tmp_path):
    return BankingService(WorkbookStore(tmp_path / "banking_master.xlsx"))


def transaction(description: str, *, category: str = "Miscellaneous", review: bool = True,
                amount: str = "-10.00", transfer_status: str = "none") -> Transaction:
    normalized = description.upper()
    return Transaction(
        transaction_id=f"test-{abs(hash(description))}",
        fingerprint=f"fingerprint-{abs(hash(description))}",
        date=date(2026, 8, 1),
        bank="CommBank",
        account="xx2990",
        original_description=description,
        normalized_description=normalized,
        amount=Decimal(amount),
        balance=Decimal("100.00"),
        transaction_type="debit" if Decimal(amount) < 0 else "credit",
        category=category,
        transfer_status=transfer_status,
        review_required=review,
        source_file="lookup-test.csv",
        source_row=1,
        imported_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_curated_lookup_covers_requested_brands_and_specificity(tmp_path):
    svc = service(tmp_path)
    svc.install_curated_lookup()
    _, categories, rules, _, _, _ = svc.state()

    expected = {
        "COLES BRISBANE": "Groceries",
        "PAYMENT TO DHANUK": "Friends & Family",
        "PAYMENT TO MAHITH": "Friends & Family",
        "PAYMENT TO MALIK": "Friends & Family",
        "PAYMENT TO PO": "Friends & Family",
        "PAYMENT TO NIDHI": "Friends & Family",
        "OPENAI CHATGPT": "Phone & Subscriptions",
        "YOUTUBE PREMIUM": "Phone & Subscriptions",
        "GOOGLE ONE": "Phone & Subscriptions",
        "NETFLIX.COM": "Phone & Subscriptions",
        "LEBARA RECHARGE": "Phone & Subscriptions",
        "VODAFONE BILL": "Phone & Subscriptions",
        "TELSTRA MOBILE": "Phone & Subscriptions",
        # The specific delivery rule must win over the broader UBER transport rule.
        "UBER EATS MELBOURNE": "Eating Out",
        "UBER TRIP MELBOURNE": "Transport",
        # PO must be treated as a complete name, not a substring of SPOTIFY.
        "SPOTIFY PREMIUM": "Phone & Subscriptions",
    }
    assert {category.name for category in categories} >= set(expected.values())
    for description, category in expected.items():
        actual, review = svc.categorize(transaction(description), categories, rules)
        assert actual == category, description
        assert review is False

    category, review = svc.categorize(transaction("SPOON KITCHENWARE"), categories, rules)
    assert category == "Miscellaneous"
    assert review is True


def test_exact_merchant_rule_has_priority_over_curated_keyword(tmp_path):
    svc = service(tmp_path)
    svc.install_curated_lookup()
    svc.create_rule({
        "match_type": "exact",
        "pattern": "COLES BRISBANE",
        "category": "Eating Out",
    })
    _, categories, rules, _, _, _ = svc.state()

    category, review = svc.categorize(transaction("Coles Brisbane"), categories, rules)

    assert category == "Eating Out"
    assert review is False


def test_curated_lookup_covers_observed_merchant_and_memo_patterns(tmp_path):
    """Rules are restricted to descriptions corroborated by local samples."""
    svc = service(tmp_path)
    svc.install_curated_lookup()
    _, categories, rules, _, _, _ = svc.state()

    expected = {
        # LearningMaterials/Expenses 2026.xlsx, Expenses rows 9 and 18.
        "Transfer To Daily Anay CommBank App Brain and bots": "Education",
        "Transfer To M NISWER ISMAIL PayID Phone Electric bill- WiFi bill": "Utilities",
        # LearningMaterials/CSVData.csv contains these formerly unresolved
        # merchant/memo forms.
        "Origin Kebabs BRISBANE AUS Card xx1438": "Eating Out",
        "HJs Beak House Brisbane": "Eating Out",
        "HOLLAND PARK CHEMPRQPS HOLLAND PARK": "Health",
        "SP BARBER TEMPLE South Brisbane": "Personal Care",
        "Direct Debit GLOFOXPAYMENT SnapFitness": "Health",
        # CommBank truncates the final merchant token in the supplied row.
        "Direct Debit 507156 GLOFOXPAYMENT SnapFitne_V9drDXV3": "Health",
        "HOLLAND PARK FITNESS PTY": "Health",
        "DiDiMobility Sydney AU": "Transport",
        "Transfer To M SALGAMA HEWAGE PayID Phone Woolies": "Groceries",
        "Transfer To Daily Anay CommBank App Grocery": "Groceries",
        "Transfer To Daily Anay CommBank App Transport": "Transport",
    }
    for description, expected_category in expected.items():
        actual, review = svc.categorize(transaction(description), categories, rules)
        assert actual == expected_category, description
        assert review is False


def test_curated_lookup_keeps_ambiguous_people_and_investment_payments_for_review(tmp_path):
    svc = service(tmp_path)
    svc.install_curated_lookup()
    _, categories, rules, _, _, _ = svc.state()

    for description in (
        "Transfer To Farzad Hayatbakhsh PayID Phone from CommBank App",
        "PayTo Webull Securities Australia Pty monoova-webull-037VM6",
        "UQIES",
        "Transfer To Daily Anay CommBank App Work",
    ):
        category, review = svc.categorize(transaction(description), categories, rules)
        assert category == "Miscellaneous", description
        assert review is True


def test_curated_migration_preserves_manual_choices_and_is_idempotent(tmp_path):
    svc = service(tmp_path)
    txs, categories, rules, accounts, history, _ = svc.state()
    categories.append(Category(id="manual-choice", name="Manual choice"))
    txs.extend([
        transaction("COLES WEST END"),
        transaction("OPENAI SUBSCRIPTION"),
        transaction("PAYMENT TO DHANUK"),
        # A manual decision is represented by a non-Miscellaneous category and
        # must remain untouched even when the description matches a lookup.
        transaction("COLES MANUAL OVERRIDE", category="Manual choice", review=False),
        # Transfer review remains visible after its category is filled in.
        transaction("TRANSFER TO MAHITH", transfer_status="suspected"),
    ])
    svc.persist(txs, categories, rules, accounts, history, recompute=False)

    svc.install_curated_lookup()
    migrated, migrated_categories, migrated_rules, _, _, _ = svc.state()
    by_description = {tx.original_description: tx for tx in migrated}

    assert by_description["COLES WEST END"].category == "Groceries"
    assert by_description["OPENAI SUBSCRIPTION"].category == "Phone & Subscriptions"
    assert by_description["PAYMENT TO DHANUK"].category == "Friends & Family"
    assert by_description["COLES MANUAL OVERRIDE"].category == "Manual choice"
    assert by_description["COLES MANUAL OVERRIDE"].review_required is False
    assert by_description["TRANSFER TO MAHITH"].category == "Friends & Family"
    assert by_description["TRANSFER TO MAHITH"].review_required is True

    category_count = len(migrated_categories)
    rule_count = len(migrated_rules)
    snapshot = [(tx.original_description, tx.category, tx.review_required) for tx in migrated]

    svc.install_curated_lookup()
    again, categories_again, rules_again, _, _, _ = svc.state()

    assert len(categories_again) == category_count
    assert len(rules_again) == rule_count
    assert [(tx.original_description, tx.category, tx.review_required) for tx in again] == snapshot
