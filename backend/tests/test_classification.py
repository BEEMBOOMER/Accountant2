from decimal import Decimal

from backend.app.services import BankingService
from backend.app.workbook import WorkbookStore


def test_paired_savings_correction_updates_summary_and_drilldown(tmp_path):
    service = BankingService(WorkbookStore(tmp_path / "banking_master.xlsx"))
    statement = "\n".join((
        "Bank Account,Date,Narrative,Debit Amount,Credit Amount,Balance",
        "034001844999,10/08/2026,WITHDRAWAL MOBILE TFR Westpac Lif,50.00,,100.00",
        "734001872217,10/08/2026,DEPOSIT ONLINE TFR Westpac Cho,,50.00,100.00",
    ))
    service.import_csv(statement, bank="Westpac", account=None, source_file="pair.csv")
    inbound = next(tx for tx in service.state()[0] if tx.amount > 0)
    # A manual savings decision is applied coherently to the matched group.
    service.set_classification(inbound.transaction_id, "savings")
    assert service.analytics("2026-08")["savings"] == Decimal("50.00")
    assert len(service.metric_transactions("savings", "2026-08")) == 1

    service.set_classification(inbound.transaction_id, "transfer")
    assert service.analytics("2026-08")["savings"] == Decimal("0.00")
    assert service.metric_transactions("savings", "2026-08") == []


def test_explicit_westpac_savings_beats_nearby_masked_commbank_transfer(tmp_path):
    service = BankingService(WorkbookStore(tmp_path / "banking_master.xlsx"))
    service.import_csv(
        "\n".join((
            "04/08/2026,-2000.00,Transfer to xx2990 CommBank app,5000.00",
            "06/08/2026,-2000.00,Transfer To WestPac Savings CommBank App Savings account,3000.00",
        )),
        bank="CommBank", account="commbank-main", source_file="commbank.csv",
    )
    service.import_csv(
        "\n".join((
            "Bank Account,Date,Narrative,Debit Amount,Credit Amount,Balance",
            "034001844999,06/08/2026,DEPOSIT-OSKO PAYMENT ANAY VENUGOPAL Savings account,,2000.00,5000.00",
        )),
        bank="Westpac", account=None, source_file="westpac.csv",
    )
    summary = service.analytics("2026-08")
    rows = service.state()[0]
    masked = next(tx for tx in rows if "xx2990" in tx.original_description.lower())
    savings_outbound = next(tx for tx in rows if "WestPac Savings" in tx.original_description)
    assert masked.transfer_status == "confirmed"
    assert masked.transfer_group_id != savings_outbound.transfer_group_id
    assert summary["savings"] == Decimal("2000.00")
    assert summary["income"] == Decimal("0.00")
    assert summary["expenditure"] == Decimal("0.00")
