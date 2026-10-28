from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from common.views import SUPERVISORS

from .forms import ReportRequestForm
from .models import ReportRun
from .pdf import render_pdf
from .tasks import build_report

REPORT_ROLES = SUPERVISORS + ("accountant",)


def _check(request):
    if not request.user.has_role(*REPORT_ROLES):
        raise PermissionDenied


@login_required
def report_home(request):
    _check(request)
    form = ReportRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        run = ReportRun.objects.create(
            kind=form.cleaned_data["kind"], report_date=form.cleaned_data["report_date"], requested_by=request.user
        )
        result = build_report.delay(run.pk)
        task_id = getattr(result, "id", "") or ""
        if task_id:
            ReportRun.objects.filter(pk=run.pk).update(task_id=str(task_id))
        return redirect("reports:detail", pk=run.pk)
    return render(request, "reports/home.html", {"form": form, "runs": ReportRun.objects.select_related("requested_by")[:15]})


def _page_number(request, total):
    try:
        number = int(request.GET.get("page", 1))
    except ValueError:
        number = 1
    return min(max(number, 1), max(total, 1))


@login_required
def report_detail(request, pk):
    _check(request)
    run = get_object_or_404(ReportRun, pk=pk)
    return render(request, "reports/detail.html", _body_context(request, run))


@login_required
def report_body(request, pk):
    """HTMX partial. Polls until the report finishes, then shows the viewer."""
    _check(request)
    run = get_object_or_404(ReportRun, pk=pk)
    return render(request, "reports/_body.html", _body_context(request, run))


def _body_context(request, run):
    pages = run.pages
    number = _page_number(request, len(pages))
    return {
        "run": run,
        "pages": pages,
        "total": len(pages),
        "number": number,
        "page": pages[number - 1] if pages else None,
        "prev_page": number - 1 if number > 1 else None,
        "next_page": number + 1 if number < len(pages) else None,
    }


@login_required
def report_pdf(request, pk):
    """Print a page range. Start/end come from the boxes under the viewer."""
    _check(request)
    run = get_object_or_404(ReportRun, pk=pk, status=ReportRun.Status.DONE)
    total = len(run.pages)

    def number(name, default):
        try:
            return int(request.GET.get(name, default))
        except ValueError:
            return default

    start, end, copies = number("start", 1), number("end", total), min(max(number("copies", 1), 1), 20)
    if start < 1 or end > total or start > end:
        messages.error(request, f"Choose pages between 1 and {total}, with Start Page not after End Page.")
        return redirect("reports:detail", pk=pk)
    pdf = render_pdf(run, start, end, copies)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{run.kind}-{run.report_date:%Y%m%d}-p{start}-{end}.pdf"'
    return response
