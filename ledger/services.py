from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from common.utils import money

from . import chart
from .models import Account, Expense, JournalEntry, JournalLine

PAID_FROM_ACCOUNT = {"CASH": chart.CASH, "BANK": chart.BANK, "MPESA": chart.MPESA}


class LedgerError(Exception):
    pass


@transaction.atomic
def post_journal(*, date, memo, lines, source="", user=None):
    """Post a balanced journal entry.

    lines is a list of (account_code, debit, credit) tuples. Zero lines are
    skipped. Debits must equal credits to the cent.
    """
    cleaned = []
    for code, debit, credit in lines:
        debit, credit = money(debit), money(credit)
        if debit == 0 and credit == 0:
            continue
        if debit < 0 or credit < 0:
            raise LedgerError("Journal amounts cannot be negative.")
        cleaned.append((code, debit, credit))
    if not cleaned:
        return None
    total_debit = sum(d for _, d, _ in cleaned)
    total_credit = sum(c for _, _, c in cleaned)
    if total_debit != total_credit:
        raise LedgerError(f"Journal does not balance: debits {total_debit} vs credits {total_credit}.")

    accounts = {a.code: a for a in Account.objects.filter(code__in={c for c, _, _ in cleaned})}
    missing = {c for c, _, _ in cleaned} - set(accounts)
    if missing:
        raise LedgerError(f"Missing ledger accounts: {', '.join(sorted(missing))}. Run: python manage.py seed_bonje")

    entry = JournalEntry.objects.create(date=date, memo=memo[:200], source=source[:60], posted_by=user)
    JournalLine.objects.bulk_create(
        [JournalLine(entry=entry, account=accounts[c], debit=d, credit=cr) for c, d, cr in cleaned]
    )
    return entry


@transaction.atomic
def post_expense(expense: Expense, user=None):
    entry = post_journal(
        date=expense.date,
        memo=expense.description,
        lines=[
            (expense.account.code, expense.amount, 0),
            (PAID_FROM_ACCOUNT[expense.paid_from], 0, expense.amount),
        ],
        source=f"ledger.Expense:{expense.pk}",
        user=user,
    )
    expense.journal = entry
    expense.save(update_fields=["journal", "updated_at"])
    return entry


def trial_balance(as_of):
    """Rows of (account, debit, credit) with each account's net balance on its normal side."""
    zero = Value(Decimal("0"), output_field=DecimalField())
    totals = (
        JournalLine.objects.filter(entry__date__lte=as_of)
        .values("account_id")
        .annotate(d=Coalesce(Sum("debit"), zero), c=Coalesce(Sum("credit"), zero))
    )
    by_account = {row["account_id"]: (row["d"], row["c"]) for row in totals}
    rows = []
    for account in Account.objects.all():
        d, c = by_account.get(account.pk, (Decimal("0"), Decimal("0")))
        net = d - c
        if net == 0:
            continue
        rows.append((account, net if net > 0 else Decimal("0"), -net if net < 0 else Decimal("0")))
    return rows


def receivables_total():
    from sales.models import Customer

    return sum((c.balance for c in Customer.objects.all()), Decimal("0"))
