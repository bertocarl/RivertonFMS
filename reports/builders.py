"""Report calculations. Each builder returns {"title", "subtitle", "sections": [...]}.

A section is {"title", "columns", "rows", "totals"?, "note"?}. Values are
pre-formatted strings so the viewer and PDF stay trivial.
"""
from decimal import Decimal

from django.conf import settings
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from common.utils import D, fmt, money
from forecourt.models import Product, StockMovement, Tank
from ledger.services import trial_balance
from sales.models import Customer, Sale
from shifts.models import MeterReading, Shift, TankDip

ZERO = Value(Decimal("0"), output_field=DecimalField())
CURRENCY = settings.CURRENCY


def _signed(value):
    return fmt(value) if value >= 0 else f"({fmt(abs(value))})"


def build_dssr(report_date):
    """Daily Station Sales Report: pump meters, stock, sales by payment, shift variances."""
    shifts = list(
        Shift.objects.filter(business_date=report_date, status__in=["VERIFIED", "CLOSED"]).order_by("opened_at")
    )
    shift_ids = [s.pk for s in shifts]

    # 1. Pump meter matrix
    meter_rows, tot_l, tot_v, tot_e = [], Decimal("0"), Decimal("0"), Decimal("0")
    readings = MeterReading.objects.filter(shift_id__in=shift_ids).select_related(
        "shift", "nozzle__pump", "nozzle__tank__product"
    ).order_by("shift__opened_at", "nozzle__pump__number", "nozzle__number")
    for r in readings:
        litres, value, electric = r.litres_sold, r.expected_value, r.electric_cash
        tot_l, tot_v, tot_e = tot_l + litres, tot_v + value, tot_e + electric
        meter_rows.append(
            [
                r.shift.code, f"P{r.nozzle.pump.number}-N{r.nozzle.number}", r.nozzle.tank.product.name,
                fmt(r.opening_litres), fmt(r.closing_litres), fmt(litres), fmt(r.unit_price),
                fmt(value), fmt(electric), _signed(electric - value),
            ]
        )
    meters = {
        "title": "Pump meter matrix",
        "columns": ["Shift", "Nozzle", "Product", "Opening L", "Closing L", "Litres", "Price", "Value", "Electric cash", "Diff"],
        "rows": meter_rows,
        "totals": ["Total", "", "", "", "", fmt(tot_l), "", fmt(tot_v), fmt(tot_e), _signed(tot_e - tot_v)],
    }

    # 2. Stock reconciliation (fuel)
    stock_rows = []
    for product in Product.objects.filter(kind="FUEL", is_active=True):
        tanks = list(Tank.objects.filter(product=product))
        on_hand = sum((t.current_level for t in tanks), Decimal("0"))
        moves = StockMovement.objects.filter(product=product)
        after = moves.filter(business_date__gte=report_date).aggregate(t=Coalesce(Sum("quantity"), ZERO))["t"]
        day = moves.filter(business_date=report_date)
        receipts = day.filter(reason="PURCHASE").aggregate(t=Coalesce(Sum("quantity"), ZERO))["t"]
        sold = -day.filter(reason__in=["METER", "SALE"]).aggregate(t=Coalesce(Sum("quantity"), ZERO))["t"]
        adjust = day.filter(reason="ADJ").aggregate(t=Coalesce(Sum("quantity"), ZERO))["t"]
        opening = on_hand - after
        book_close = opening + receipts - sold + adjust

        dip_total, dips_found = Decimal("0"), 0
        latest = {}
        for dip in TankDip.objects.filter(
            shift__business_date=report_date, phase="CLOSE", tank__in=tanks
        ).order_by("measured_at"):
            latest[dip.tank_id] = dip.litres
        dips_found = len(latest)
        dip_total = sum(latest.values(), Decimal("0"))
        if tanks and dips_found == len(tanks):
            variance = dip_total - book_close
            dip_cell, var_cell = fmt(dip_total), _signed(variance)
            pct = fmt((variance / sold * 100) if sold else Decimal("0")) + "%"
        else:
            dip_cell, var_cell, pct = "no dip", "—", "—"
        stock_rows.append(
            [product.name, fmt(opening), fmt(receipts), fmt(sold), fmt(adjust), fmt(book_close), dip_cell, var_cell, pct]
        )
    stock = {
        "title": "Fuel stock reconciliation (litres)",
        "columns": ["Product", "Opening", "Receipts", "Sold", "Adjustments", "Book closing", "Closing dip", "Dip variance", "% of sales"],
        "rows": stock_rows,
        "note": "Dip variance is the closing dip minus book stock. Negative means fuel is unaccounted for.",
    }

    # 3. Sales by product and payment method
    methods = ["CASH", "MPESA", "CARD", "CREDIT"]
    sales_rows, col_totals = [], {m: Decimal("0") for m in methods}
    grand_qty = Decimal("0")
    grouped = (
        Sale.objects.filter(shift_id__in=shift_ids)
        .values("product__name", "payment_method")
        .annotate(amount=Coalesce(Sum("amount"), ZERO), qty=Coalesce(Sum("quantity"), ZERO))
    )
    table = {}
    for g in grouped:
        row = table.setdefault(g["product__name"], {"qty": Decimal("0"), **{m: Decimal("0") for m in methods}})
        row[g["payment_method"]] += g["amount"]
        row["qty"] += g["qty"]
    for name in sorted(table):
        row = table[name]
        total = sum(row[m] for m in methods)
        for m in methods:
            col_totals[m] += row[m]
        grand_qty += row["qty"]
        sales_rows.append([name, fmt(row["qty"], 3), *[fmt(row[m]) for m in methods], fmt(total)])
    sales = {
        "title": f"Sales by product and payment ({CURRENCY})",
        "columns": ["Product", "Quantity", "Cash", "M-Pesa", "Card", "Credit", "Total"],
        "rows": sales_rows,
        "totals": ["Total", fmt(grand_qty, 3), *[fmt(col_totals[m]) for m in methods], fmt(sum(col_totals.values(), Decimal("0")))],
    }

    # 4. Shift position
    from shifts.services import shift_summary

    shift_rows, short_total = [], Decimal("0")
    for s in shifts:
        summary = shift_summary(s)
        short_total += summary["shortage"]
        shift_rows.append(
            [
                s.code, str(s.opened_by), fmt(summary["metered_value"]), fmt(summary["recorded_fuel_value"]),
                _signed(summary["shortage"]), s.get_status_display(), "Yes" if s.backed_up_at else "No",
            ]
        )
    position = {
        "title": "Shift cash position",
        "columns": ["Shift", "Opened by", "Metered value", "Recorded fuel sales", "Shortage", "Status", "Backed up"],
        "rows": shift_rows,
        "totals": ["Total", "", "", "", _signed(short_total), "", ""],
        "note": "A positive shortage means metered fuel value exceeds the sales recorded.",
    }

    return {
        "title": "Daily Station Sales Report (DSSR)",
        "subtitle": f"Business date {report_date:%d/%m/%Y}. {len(shifts)} shift(s).",
        "sections": [meters, stock, sales, position],
    }


def build_trial(as_of):
    rows, debit_total, credit_total = [], Decimal("0"), Decimal("0")
    for account, debit, credit in trial_balance(as_of):
        debit_total += debit
        credit_total += credit
        rows.append([account.code, account.name, account.get_type_display(), fmt(debit) if debit else "", fmt(credit) if credit else ""])
    return {
        "title": "Trial balance",
        "subtitle": f"As at {as_of:%d/%m/%Y}",
        "sections": [
            {
                "title": f"Trial balance ({CURRENCY})",
                "columns": ["Code", "Account", "Type", "Debit", "Credit"],
                "rows": rows,
                "totals": ["", "Total", "", fmt(debit_total), fmt(credit_total)],
                "note": "Balanced." if debit_total == credit_total else "WARNING: the ledger does not balance.",
            }
        ],
    }


def build_debtors(as_of):
    rows, total = [], Decimal("0")
    for customer in Customer.objects.all():
        balance = customer.balance
        if balance <= 0:
            continue
        oldest = customer.invoices.filter(status="OPEN").order_by("issue_date").first()
        age = (as_of - oldest.issue_date).days if oldest else 0
        total += balance
        rows.append(
            [customer.name, customer.phone, fmt(customer.credit_limit), fmt(customer.invoiced), fmt(customer.paid),
             fmt(balance), fmt(oldest.issue_date) if oldest else "—", str(age)]
        )
    return {
        "title": "Credit customers (debtors)",
        "subtitle": f"As at {as_of:%d/%m/%Y}",
        "sections": [
            {
                "title": f"Amounts owed ({CURRENCY})",
                "columns": ["Customer", "Phone", "Credit limit", "Invoiced", "Paid", "Balance", "Oldest invoice", "Days"],
                "rows": rows,
                "totals": ["Total", "", "", "", "", fmt(total), "", ""],
            }
        ],
    }


BUILDERS = {"DSSR": build_dssr, "TRIAL": build_trial, "DEBTORS": build_debtors}
