from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from openpyxl import load_workbook

from backend.app.services import BankingService, ValidationError
from backend.app.workbook import WorkbookStore


ROOT = Path(__file__).resolve().parents[2]


def service(tmp_path):
    return BankingService(WorkbookStore(tmp_path / "banking_master.xlsx"))


def test_duplicate_and_overlap_imports_are_idempotent(tmp_path):
    svc = service(tmp_path)
    text = (ROOT / "LearningMaterials" / "CSVData.csv").read_text(encoding="utf-8")
    first = svc.import_csv(text, bank="CommBank", account="commbank-main", source_file="c.csv")
    second = svc.import_csv(text, bank="CommBank", account="commbank-main", source_file="c.csv")
    assert first.inserted == 16
    assert second.inserted == 0
    assert second.duplicates == 16
    assert len(svc.state()[0]) == 16


def test_partially_overlapping_statement_only_adds_unseen_rows(tmp_path):
    svc = service(tmp_path)
    text = (ROOT / "LearningMaterials" / "CSVData.csv").read_text(encoding="utf-8")
    rows = text.splitlines()
    subset = "\n".join(rows[:5])
    first = svc.import_csv(subset, bank="CommBank", account="commbank-main", source_file="partial.csv")
    overlap = svc.import_csv(text, bank="CommBank", account="commbank-main", source_file="full.csv")
    assert first.inserted == 5
    assert overlap.duplicates == 5
    assert overlap.inserted == 11
    assert len(svc.state()[0]) == 16


def test_concurrent_retries_cannot_overwrite_or_duplicate_rows(tmp_path):
    svc = service(tmp_path)
    text = (ROOT / "LearningMaterials" / "CSVData.csv").read_text(encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda index: svc.import_csv(text, bank="CommBank", account="commbank-main", source_file=f"retry-{index}.csv"),
            range(2),
        ))
    assert sum(result.inserted for result in results) == 16
    assert len(svc.state()[0]) == 16


def test_workbook_round_trip_preserves_summary_and_categories(tmp_path):
    svc = service(tmp_path)
    text = (ROOT / "LearningMaterials" / "Data_export_11082026.csv").read_text(encoding="utf-8")
    result = svc.import_csv(text, bank="Westpac", account=None, source_file="w.csv")
    assert result.inserted == 43
    transactions, categories, rules, accounts, history, summaries = svc.state()
    assert transactions and history and summaries
    assert any(s.category_totals for s in summaries)
    assert any(t.category == "Transport" for t in transactions)


def test_manual_transfer_confirmation_excludes_cashflow_and_tracks_savings(tmp_path):
    svc = service(tmp_path)
    commbank = (ROOT / "LearningMaterials" / "CSVData.csv").read_text(encoding="utf-8")
    westpac = (ROOT / "LearningMaterials" / "Data_export_11082026.csv").read_text(encoding="utf-8")
    svc.import_csv(commbank, bank="CommBank", account="commbank-main", source_file="c.csv")
    svc.import_csv(westpac, bank="Westpac", account=None, source_file="w.csv")
    transactions = svc.state()[0]
    candidate = next(t for t in transactions if t.transfer_status == "suspected")
    group = candidate.transfer_group_id
    before = svc.analytics("2026-08")

    svc.set_category(candidate.transaction_id, "Miscellaneous")
    still_pending = next(t for t in svc.state()[0] if t.transaction_id == candidate.transaction_id)
    assert still_pending.review_required is True

    svc.set_transfer(candidate.transaction_id, "confirmed")
    related = [t for t in svc.state()[0] if t.transfer_group_id == group]
    after = svc.analytics("2026-08")

    assert len(related) == 2
    assert all(t.transfer_status == "confirmed" and t.internal_transfer for t in related)
    assert after["income"] <= before["income"]
    assert after["expenditure"] <= before["expenditure"]


def test_unknown_accounts_empty_rules_and_invalid_workbook_money_fail_closed(tmp_path):
    svc = service(tmp_path)
    westpac = "Bank Account,Date,Narrative,Debit Amount,Credit Amount,Balance,Categories,Serial\n999,01/08/2026,TEST,1.00,,4.00,PAYMENT,\n"
    with pytest.raises(ValidationError, match="configure these statement accounts"):
        svc.import_csv(westpac, bank="Westpac", account=None, source_file="unknown.csv")
    with pytest.raises(ValidationError, match="pattern is required"):
        svc.create_rule({"match_type": "keyword", "pattern": " ", "category": "Groceries"})

    workbook = load_workbook(svc.store.path)
    workbook["Transactions"].append([
        "broken", "broken", "2026-08-01", "Westpac", "734001872217", "Bad row", "BAD ROW",
        "not-money", 1, "debit", "Miscellaneous", "none", False, None, False, True,
        "manual.csv", 1, "2026-08-01T00:00:00+10:00",
    ])
    workbook.save(svc.store.path)
    workbook.close()
    with pytest.raises(RuntimeError, match="invalid Transactions row"):
        svc.state()


def test_referenced_account_identity_cannot_change(tmp_path):
    svc = service(tmp_path)
    text = (ROOT / "LearningMaterials" / "CSVData.csv").read_text(encoding="utf-8")
    svc.import_csv(text, bank="CommBank", account="commbank-main", source_file="c.csv")
    with pytest.raises(ValidationError, match="cannot be changed"):
        svc.update_account("commbank-main", {"identifier": "different"})
    renamed = svc.update_account("commbank-main", {"name": "Everyday spending"})
    assert renamed.name == "Everyday spending"
