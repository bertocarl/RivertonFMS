import json
from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from common.utils import money
from forecourt.models import Nozzle
from forecourt.stock import move_stock
from ledger import chart
from ledger.services import post_journal

from .models import MeterReading, Shift

TOLERANCE = Decimal("1.00")


class ShiftError(Exception):
    pass


def get_open_shift(station=None):
    qs = Shift.objects.filter(status=Shift.Status.OPEN)
    if station:
        qs = qs.filter(station=station)
    return qs.first()


@transaction.atomic
def open_shift(station, user, notes=""):
    if Shift.objects.filter(station=station, status__in=[Shift.Status.OPEN, Shift.Status.VERIFIED]).exists():
        raise ShiftError("A shift is already open. Close it before opening another.")
    today = timezone.localdate()
    prefix = f"{station.code}-{today:%Y%m%d}-"
    number = Shift.objects.filter(code__startswith=prefix).count() + 1
    shift = Shift.objects.create(station=station, code=f"{prefix}{number}", opened_by=user, notes=notes)
    nozzles = Nozzle.objects.filter(is_active=True, pump__is_active=True, pump__station=station).select_related(
        "tank__product", "pump"
    )
    for nozzle in nozzles:
        last = (
            MeterReading.objects.filter(nozzle=nozzle, shift__status=Shift.Status.CLOSED, closing_litres__isnull=False)
            .order_by("-shift__closed_at")
            .first()
        )
        MeterReading.objects.create(
            shift=shift,
            nozzle=nozzle,
            opening_litres=last.closing_litres if last else nozzle.totalizer_volume,
            opening_cash_meter=last.closing_cash_meter if last else nozzle.totalizer_amount,
            unit_price=nozzle.tank.product.selling_price,
        )
    return shift


def pull_totalizers(shift):
    """Fill closing meters from the latest totalizer values pushed by the pumps."""
    if not shift.is_open:
        raise ShiftError("Only an open shift can be changed.")
    updated = 0
    for reading in shift.readings.select_related("nozzle"):
        n = reading.nozzle
        if n.totalizer_volume >= reading.opening_litres and n.totalizer_volume > 0:
            reading.closing_litres = n.totalizer_volume
            reading.closing_cash_meter = n.totalizer_amount
            reading.save(update_fields=["closing_litres", "closing_cash_meter"])
            updated += 1
    return updated


def shift_summary(shift):
    from sales.models import Sale

    readings = list(shift.readings.select_related("nozzle__pump", "nozzle__tank__product"))
    zero = Value(Decimal("0"), output_field=DecimalField())
    fuel_sales = Sale.objects.filter(shift=shift, product__kind="FUEL")
    recorded = fuel_sales.aggregate(v=Coalesce(Sum("amount"), zero), q=Coalesce(Sum("quantity"), zero))
    by_method = {
        row["payment_method"]: row["t"]
        for row in Sale.objects.filter(shift=shift).values("payment_method").annotate(t=Coalesce(Sum("amount"), zero))
    }
    metered_value = sum((r.expected_value for r in readings), Decimal("0"))
    metered_litres = sum((r.litres_sold for r in readings), Decimal("0"))
    electric_total = sum((r.electric_cash for r in readings), Decimal("0"))
    incomplete = [r for r in readings if not r.is_complete]
    electric_mismatch = [r for r in readings if r.is_complete and abs(r.electric_cash - r.expected_value) > TOLERANCE]
    shortage = metered_value - recorded["v"]
    return {
        "readings": readings,
        "metered_litres": metered_litres,
        "metered_value": metered_value,
        "electric_total": electric_total,
        "recorded_fuel_value": recorded["v"],
        "recorded_fuel_litres": recorded["q"],
        "by_method": by_method,
        "total_sales": sum(by_method.values(), Decimal("0")),
        "shortage": shortage,
        "incomplete": incomplete,
        "electric_mismatch": electric_mismatch,
        "needs_acknowledgement": abs(shortage) > TOLERANCE or bool(electric_mismatch),
    }


@transaction.atomic
def verify_shift(shift, user, business_date, accept_variance=False):
    if shift.status != Shift.Status.OPEN:
        raise ShiftError("This shift is not open.")
    if business_date > timezone.localdate():
        raise ShiftError("The date cannot be in the future.")
    summary = shift_summary(shift)
    if summary["incomplete"]:
        names = ", ".join(str(r.nozzle) for r in summary["incomplete"])
        raise ShiftError(f"Closing meters are missing for: {names}.")
    if summary["needs_acknowledgement"] and not accept_variance:
        raise ShiftError("There is a shortage or meter mismatch. Tick the box to accept it, or fix the entries.")
    shift.business_date = business_date
    shift.status = Shift.Status.VERIFIED
    shift.verified_by = user
    shift.verified_at = timezone.now()
    shift.variance_accepted = summary["needs_acknowledgement"]
    shift.save()
    return summary


@transaction.atomic
def reopen_shift(shift):
    if shift.status != Shift.Status.VERIFIED:
        raise ShiftError("Only a verified shift can be reopened.")
    shift.status = Shift.Status.OPEN
    shift.business_date = None
    shift.verified_by = None
    shift.verified_at = None
    shift.backed_up_at = None
    shift.variance_accepted = False
    shift.save()


def build_backup(shift):
    from sales.models import Sale

    summary = shift_summary(shift)
    return {
        "shift": shift.code,
        "business_date": shift.business_date,
        "status": shift.status,
        "opened_at": shift.opened_at,
        "opened_by": str(shift.opened_by),
        "readings": [
            {
                "pump": r.nozzle.pump.number,
                "nozzle": r.nozzle.number,
                "product": r.nozzle.tank.product.code,
                "opening_litres": r.opening_litres,
                "closing_litres": r.closing_litres,
                "opening_electric_cash": r.opening_cash_meter,
                "closing_electric_cash": r.closing_cash_meter,
                "unit_price": r.unit_price,
            }
            for r in summary["readings"]
        ],
        "dips": [
            {"tank": d.tank.name, "phase": d.phase, "litres": d.litres} for d in shift.dips.select_related("tank")
        ],
        "sales": [
            {
                "id": s.pk,
                "product": s.product.code,
                "quantity": s.quantity,
                "unit_price": s.unit_price,
                "amount": s.amount,
                "method": s.payment_method,
                "customer": s.customer.name if s.customer else "",
                "reference": s.reference,
                "vehicle": s.vehicle_reg,
            }
            for s in Sale.objects.filter(shift=shift).select_related("product", "customer")
        ],
        "totals": {
            "metered_litres": summary["metered_litres"],
            "metered_value": summary["metered_value"],
            "recorded_fuel_value": summary["recorded_fuel_value"],
            "shortage": summary["shortage"],
            "by_method": summary["by_method"],
        },
    }


def save_backup(shift):
    """Write the shift backup to disk and stamp backed_up_at. Returns (path, json_text)."""
    text = json.dumps(build_backup(shift), cls=DjangoJSONEncoder, indent=2)
    folder = settings.STATION_BACKUP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"{shift.code}-{stamp}.json"
    path.write_text(text, encoding="utf-8")
    shift.backed_up_at = timezone.now()
    shift.save(update_fields=["backed_up_at", "updated_at"])
    return path, text


@transaction.atomic
def close_shift(shift, user):
    if shift.status != Shift.Status.VERIFIED:
        raise ShiftError("Verify the shift and enter its date before closing.")
    if not shift.business_date:
        raise ShiftError("The shift has no date. Verify it again.")
    if not shift.backed_up_at:
        raise ShiftError("Back up the shift data before closing.")

    summary = shift_summary(shift)
    cogs = Decimal("0")
    for reading in summary["readings"]:
        litres = reading.litres_sold
        nozzle = reading.nozzle
        if litres:
            move_stock(
                product=nozzle.tank.product,
                quantity=-litres,
                reason="METER",
                business_date=shift.business_date,
                reference=shift.code,
                tank=nozzle.tank,
                user=user,
            )
            cogs += litres * nozzle.tank.product.cost_price
        nozzle.totalizer_volume = reading.closing_litres
        nozzle.totalizer_amount = reading.closing_cash_meter
        nozzle.save(update_fields=["totalizer_volume", "totalizer_amount", "updated_at"])

    post_journal(
        date=shift.business_date,
        memo=f"Fuel cost of sales {shift.code}",
        lines=[(chart.COGS_FUEL, money(cogs), 0), (chart.INVENTORY_FUEL, 0, money(cogs))],
        source=f"shifts.Shift:{shift.pk}",
        user=user,
    )
    # Bring fuel revenue up to the metered value. A shortage is booked as a cash loss.
    shortage = money(summary["shortage"])
    if shortage > 0:
        lines = [(chart.CASH_OVER_SHORT, shortage, 0), (chart.FUEL_SALES, 0, shortage)]
    else:
        lines = [(chart.FUEL_SALES, -shortage, 0), (chart.CASH_OVER_SHORT, 0, -shortage)]
    post_journal(
        date=shift.business_date,
        memo=f"Cash over/short {shift.code}",
        lines=lines,
        source=f"shifts.Shift:{shift.pk}",
        user=user,
    )

    shift.status = Shift.Status.CLOSED
    shift.closed_by = user
    shift.closed_at = timezone.now()
    shift.save()
    return summary
