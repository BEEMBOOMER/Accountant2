from pathlib import Path
from decimal import Decimal

import pytest

from backend.app.importers import ImportErrorDetail, detect_bank, parse_commbank, parse_westpac


ROOT = Path(__file__).resolve().parents[2]


def test_commbank_sample_is_headerless_and_signed():
    text = (ROOT / "LearningMaterials" / "CSVData.csv").read_text(encoding="utf-8")
    transactions, errors = parse_commbank(text, account="xx2990", source_file="sample.csv")
    assert not errors
    assert len(transactions) == 16
    assert transactions[0].amount == Decimal("-38.95")
    assert transactions[0].original_description == "Myer Pty Ltd Docklands VI AUS Card xx1438 Value Date: 07/08/2026"


def test_bank_detection_uses_csv_structure_and_rejects_unknown_files():
    commbank = (ROOT / "LearningMaterials" / "CSVData.csv").read_text(encoding="utf-8")
    westpac = (ROOT / "LearningMaterials" / "Data_export_11082026.csv").read_text(encoding="utf-8")
    assert detect_bank(commbank) == "CommBank"
    assert detect_bank(westpac) == "Westpac"
    with pytest.raises(ImportErrorDetail, match="not recognized"):
        detect_bank("merchant,value\nshop,10\n")


def test_westpac_sample_merges_debit_and_credit_and_keeps_repeated_rows():
    text = (ROOT / "LearningMaterials" / "Data_export_11082026.csv").read_text(encoding="utf-8")
    transactions, errors = parse_westpac(text, source_file="westpac.csv")
    assert not errors
    assert len(transactions) == 43
    translink = [t for t in transactions if "TRANSLINK" in t.original_description]
    assert len(translink) > 1
    assert len({t.fingerprint for t in translink}) == len(translink)


@pytest.mark.parametrize(
    "row, message",
    [
        ("734001872217,not-a-date,TEST,1.00,,2.00,PAYMENT,", "invalid date"),
        ("734001872217,01/08/2026,TEST,1.00,1.00,2.00,PAYMENT,", "exactly one"),
        ("734001872217,01/08/2026,TEST,,,2.00,PAYMENT,", "exactly one"),
        ("734001872217,01/08/2026,TEST,bad,,2.00,PAYMENT,", "invalid debit amount"),
        ("734001872217,01/08/2026,TEST,NaN,,2.00,PAYMENT,", "invalid debit amount"),
        ("734001872217,01/08/2026,TEST,-2.00,,2.00,PAYMENT,", "debit amount must not be negative"),
        ("734001872217,01/08/2026,TEST,,-2.00,2.00,PAYMENT,", "credit amount must not be negative"),
    ],
)
def test_westpac_rejects_malformed_rows(row, message):
    header = "Bank Account,Date,Narrative,Debit Amount,Credit Amount,Balance,Categories,Serial"
    transactions, errors = parse_westpac(f"{header}\n{row}\n", source_file="bad.csv")
    assert transactions == []
    assert message in errors[0]


def test_commbank_requires_exactly_four_columns_and_finite_money():
    extra = '01/08/2026,"-1.00","TEST","9.00","unexpected"\n'
    non_finite = '01/08/2026,"NaN","TEST","9.00"\n'
    transactions, errors = parse_commbank(extra + non_finite, account="xx2990", source_file="bad.csv")
    assert transactions == []
    assert "expected exactly 4 columns" in errors[0]
    assert "invalid amount" in errors[1]
