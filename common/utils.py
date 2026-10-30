import datetime
from decimal import ROUND_HALF_UP, Decimal

TWO = Decimal("0.01")


def D(value) -> Decimal:
    """Coerce anything numeric (or None) to Decimal."""
    if value is None or value == "":
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def money(value) -> Decimal:
    return D(value).quantize(TWO, rounding=ROUND_HALF_UP)


def fmt(value, places=2):
    """Display formatting used by tables and reports."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return f"{value:,.{places}f}"
    if isinstance(value, datetime.datetime):
        return value.astimezone().strftime("%d/%m/%Y %H:%M") if value.utcoffset() is not None else value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d/%m/%Y")
    return str(value)
