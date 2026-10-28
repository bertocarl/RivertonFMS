from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from common.views import SUPERVISORS, TableListView
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from forecourt.models import Station, Tank

from . import services
from .forms import ReadingFormSet, VerifyForm, dip_form_class
from .models import MeterReading, Shift, TankDip
from .services import ShiftError


def _require(request, *roles):
    if not request.user.has_role(*roles):
        raise PermissionDenied


class ShiftList(TableListView):
    title = "Shifts"
    model = Shift
    columns = [
        ("Shift", "code"),
        ("Opened", "opened_at"),
        ("Opened by", "opened_by"),
        ("Shift date", "business_date"),
        ("Status", "get_status_display"),
        ("Backed up", lambda s: bool(s.backed_up_at)),
    ]

    def get_queryset(self):
        return Shift.objects.select_related("opened_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for row, shift in zip(ctx["rows"], ctx["object_list"]):
            row["open_url"] = shift.pk
        return ctx


@login_required
def shift_detail(request, pk):
    shift = get_object_or_404(Shift.objects.select_related("opened_by", "station"), pk=pk)
    return render(
        request,
        "shifts/detail.html",
        {"shift": shift, "s": services.shift_summary(shift), "tanks": Tank.objects.filter(is_active=True)},
    )


@login_required
@require_POST
def shift_open(request):
    _require(request, *SUPERVISORS)
    station = Station.objects.first()
    if not station:
        messages.error(request, "No station is set up yet. Run: python manage.py seed_bonje")
        return redirect("shifts:list")
    try:
        shift = services.open_shift(station, request.user)
    except ShiftError as exc:
        messages.error(request, str(exc))
        return redirect("shifts:list")
    messages.success(request, f"Shift {shift.code} opened.")
    return redirect("shifts:detail", pk=shift.pk)


@login_required
def shift_readings(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    if not shift.is_open:
        messages.error(request, "Meters can only be changed while the shift is open.")
        return redirect("shifts:detail", pk=pk)
    queryset = MeterReading.objects.filter(shift=shift).select_related("nozzle__pump", "nozzle__tank__product")
    if request.method == "POST":
        if "pull" in request.POST:
            count = services.pull_totalizers(shift)
            messages.success(request, f"Filled closing meters for {count} nozzle(s) from the pump totalizers.")
            return redirect("shifts:readings", pk=pk)
        formset = ReadingFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Meter readings saved.")
            return redirect("shifts:detail", pk=pk)
    else:
        formset = ReadingFormSet(queryset=queryset)
    return render(request, "shifts/readings.html", {"shift": shift, "formset": formset})


@login_required
def shift_dips(request, pk, phase):
    shift = get_object_or_404(Shift, pk=pk)
    phase = phase.upper()
    if phase not in TankDip.Phase.values:
        return redirect("shifts:detail", pk=pk)
    if not shift.is_open:
        messages.error(request, "Dips can only be changed while the shift is open.")
        return redirect("shifts:detail", pk=pk)
    tanks = list(Tank.objects.filter(is_active=True).select_related("product"))
    existing = {d.tank_id: d.litres for d in shift.dips.filter(phase=phase)}
    Form = dip_form_class(tanks, existing)
    form = Form(request.POST or None)
    if request.method == "POST" and form.is_valid():
        for tank in tanks:
            litres = form.cleaned_data.get(f"tank_{tank.pk}")
            if litres is None:
                continue
            TankDip.objects.update_or_create(
                shift=shift,
                tank=tank,
                phase=phase,
                defaults={"litres": litres, "measured_by": request.user, "measured_at": timezone.now()},
            )
        messages.success(request, f"{TankDip.Phase(phase).label}s saved.")
        return redirect("shifts:detail", pk=pk)
    return render(request, "shifts/dips.html", {"shift": shift, "form": form, "phase": TankDip.Phase(phase).label})


@login_required
def shift_verify(request, pk):
    _require(request, *SUPERVISORS)
    shift = get_object_or_404(Shift, pk=pk)
    summary = services.shift_summary(shift)
    form = VerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.verify_shift(
                shift, request.user, form.cleaned_data["business_date"], form.cleaned_data["accept_variance"]
            )
        except ShiftError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Shift verified. Back up the data, then close the shift.")
            return redirect("shifts:detail", pk=pk)
    date_value = request.POST.get("business_date") or timezone.localdate().isoformat()
    return render(request, "shifts/verify.html", {"shift": shift, "s": summary, "form": form, "date_value": date_value})


@login_required
def shift_backup(request, pk):
    _require(request, *SUPERVISORS)
    shift = get_object_or_404(Shift, pk=pk)
    if shift.status == Shift.Status.OPEN:
        messages.error(request, "Verify the shift before backing it up.")
        return redirect("shifts:detail", pk=pk)
    path, text = services.save_backup(shift)
    response = HttpResponse(text, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{path.name}"'
    return response


@login_required
@require_POST
def shift_close(request, pk):
    _require(request, *SUPERVISORS)
    shift = get_object_or_404(Shift, pk=pk)
    try:
        services.close_shift(shift, request.user)
    except Exception as exc:  # ShiftError, StockError, LedgerError all carry readable messages
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Shift {shift.code} closed.")
    return redirect("shifts:detail", pk=pk)


@login_required
@require_POST
def shift_reopen(request, pk):
    _require(request, *SUPERVISORS)
    shift = get_object_or_404(Shift, pk=pk)
    try:
        services.reopen_shift(shift)
    except ShiftError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Shift reopened for corrections.")
    return redirect("shifts:detail", pk=pk)
