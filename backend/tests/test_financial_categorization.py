from decimal import Decimal

from backend.app.services import BankingService
from backend.app.workbook import WorkbookStore


def service(tmp_path):
    return BankingService(WorkbookStore(tmp_path / "banking_master.xlsx"))


def commbank_csv(*rows: tuple[str, str, str, str]) -> str:
    return "\n".join(",".join(row) for row in rows)


def westpac_csv(*rows: tuple[str, str, str, str, str]) -> str:
    lines = ["Bank Account,Date,Narrative,Debit Amount,Credit Amount,Balance"]
    for account, date, description, debit, credit in rows:
        lines.append(",".join((account, date, description, debit, credit, "10000.00")))
    return "\n".join(lines)


def test_savings_account_owner_deposit_is_confirmed_savings_without_pair(tmp_path):
    svc = service(tmp_path)
    svc.import_csv(
        westpac_csv((
            "734001872217",
            "06/08/2026",
            "DEPOSIT-OSKO PAYMENT 2223338 ANAY VENUGOPAL Savings account",
            "",
            "2000.00",
        )),
        account=None,
        source_file="savings.csv",
    )

    transactions = svc.state()[0]
    savings_deposit = transactions[0]
    analytics = svc.analytics("2026-08")

    assert savings_deposit.transfer_status == "confirmed"
    assert savings_deposit.internal_transfer is True
    assert savings_deposit.savings_transfer is True
    assert savings_deposit.review_required is False
    assert analytics["income"] == Decimal("0.00")
    assert analytics["expenditure"] == Decimal("0.00")
    assert analytics["savings"] == Decimal("2000.00")


def test_owner_deposit_with_savings_note_is_savings_on_an_everyday_account(tmp_path):
    svc = service(tmp_path)
    svc.import_csv(
        westpac_csv((
            "034001844999",
            "06/08/2026",
            "DEPOSIT-OSKO PAYMENT 2427258 ANAY VENUGOPAL Savings account",
            "",
            "2000.00",
        )),
        account=None,
        source_file="savings-note.csv",
    )

    deposit = svc.state()[0][0]
    analytics = svc.analytics("2026-08")

    assert deposit.transfer_status == "confirmed"
    assert deposit.savings_transfer is True
    assert analytics["income"] == Decimal("0.00")
    assert analytics["savings"] == Decimal("2000.00")


def test_positive_qut_payroll_is_income_even_when_qut_is_an_education_keyword(tmp_path):
    svc = service(tmp_path)
    svc.import_csv(
        commbank_csv(("01/08/2026", "2714.32", "QUT Payroll Deposit", "2714.32")),
        account="commbank-main",
        source_file="payroll.csv",
    )

    payroll = svc.state()[0][0]
    analytics = svc.analytics("2026-08")

    assert payroll.category == "Income"
    assert payroll.review_required is False
    assert analytics["income"] == Decimal("2714.32")
    assert analytics["expenditure"] == Decimal("0.00")


def test_wifi_reimbursement_offsets_phone_spending_and_is_not_income(tmp_path):
    svc = service(tmp_path)
    svc.import_csv(
        commbank_csv(
            ("01/08/2026", "-39.99", "IINET LTD N SYDNEY AUS Card xx1438 Value Date: 29/07/2026", "100.01"),
            ("02/08/2026", "13.33", "Fast Transfer From DHANUK DE SILVA to PayID Phone Dhanuk Wifi", "113.34"),
        ),
        account="commbank-main",
        source_file="wifi.csv",
    )

    by_description = {tx.original_description: tx for tx in svc.state()[0]}
    reimbursement = by_description["Fast Transfer From DHANUK DE SILVA to PayID Phone Dhanuk Wifi"]
    internet = by_description["IINET LTD N SYDNEY AUS Card xx1438 Value Date: 29/07/2026"]
    analytics = svc.analytics("2026-08")

    assert internet.category == "Phone & Subscriptions"
    assert internet.amount == Decimal("-39.99")
    assert reimbursement.category == "Phone & Subscriptions"
    assert reimbursement.expense_reimbursement is True
    assert reimbursement.review_required is False
    assert analytics["income"] == Decimal("0.00")
    assert analytics["expenditure"] == Decimal("26.66")
    phone_spend = next(item["amount"] for item in analytics["spending_by_category"] if item["category"] == "Phone & Subscriptions")
    assert phone_spend == Decimal("26.66")


def test_unrelated_ambiguous_credit_remains_income_and_needs_review(tmp_path):
    svc = service(tmp_path)
    svc.import_csv(
        commbank_csv((
            "03/08/2026",
            "9500.01",
            "Fast Transfer From Transcash International CREDIT TO ACCOUNT REMITTANCE",
            "9613.35",
        )),
        account="commbank-main",
        source_file="ambiguous-credit.csv",
    )

    credit = svc.state()[0][0]
    analytics = svc.analytics("2026-08")

    assert credit.category == "Miscellaneous"
    assert credit.transfer_status == "none"
    assert credit.review_required is True
    assert credit.expense_reimbursement is False
    assert analytics["income"] == Decimal("9500.01")
    assert analytics["expenditure"] == Decimal("0.00")
