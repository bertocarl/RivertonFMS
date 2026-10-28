from django.conf import settings


def shell(request):
    """Station name and the currently open shift, shown in the top bar."""
    ctx = {"CURRENCY": settings.CURRENCY, "station": None, "open_shift": None}
    if not request.user.is_authenticated:
        return ctx
    user = request.user
    ctx["is_supervisor"] = user.has_role("supervisor", "manager")
    ctx["is_finance"] = user.has_role("accountant", "manager")
    ctx["is_manager"] = user.has_role("manager")
    ctx["can_report"] = user.has_role("supervisor", "accountant", "manager")
    from forecourt.models import Station
    from shifts.models import Shift

    ctx["station"] = Station.objects.first()
    if ctx["station"]:
        ctx["open_shift"] = Shift.objects.filter(
            station=ctx["station"], status__in=[Shift.Status.OPEN, Shift.Status.VERIFIED]
        ).first()
    return ctx
