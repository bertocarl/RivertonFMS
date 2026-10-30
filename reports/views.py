from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from common.views import SUPERVISORS

from .forms import ReportRequestForm
from .models import ReportRun
from .pdf import render_pdf
# from .tasks import build_report

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template
from django.urls import reverse
from django.views.generic import CreateView, ListView, UpdateView
from xhtml2pdf import pisa

from .models import Invoice
from .utils import fmt, generate_etims_qr_code


FINANCE = ("accountant", "manager")

class RoleMixin(LoginRequiredMixin, UserPassesTestMixin):
    roles = None
    def test_func(self):
        user = self.request.user
        return self.roles is None or user.has_role(*self.roles)
    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()

def render_cell(obj, spec):
    if callable(spec):
        value = spec(obj)
    else:
        value = obj
        for part in spec.split("__"):
            value = getattr(value, part, None)
            if callable(value):
                value = value()
            if value is None:
                break
    return fmt(value)

class TableListView(RoleMixin, ListView):
    template_name = "generic/list.html"
    title = ""
    columns = []
    add_url = None
    add_label = "Add"
    edit_url = None
    paginate_by = 50

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title
        ctx["headers"] = [c[0] for c in self.columns]
        ctx["add_url"] = reverse(self.add_url) if self.add_url else None
        ctx["add_label"] = self.add_label
        ctx["rows"] = [
            {
                "cells": [render_cell(obj, c[1]) for c in self.columns],
                "edit": reverse(self.edit_url, args=[obj.pk]) if self.edit_url else None,
            }
            for obj in ctx["object_list"]
        ]
        return ctx

class InvoiceListView(TableListView):
    roles = FINANCE
    title = "Invoices & eTIMS Management"
    model = Invoice
    
    columns = [
        ("Invoice ID", "id"),
        ("Total Amount", "total_amount"),
        ("eTIMS Status", "etims_status"),
        ("Receipt No", "etims_receipt_number"),
        ("Actions", lambda obj: (
            f'<a href="{reverse("reports:download-invoice-pdf", args=[obj.pk])}" class="btn-pdf-download" target="_blank">📄 Download PDF</a>'
            if obj.etims_status == "TRANSMITTED" else
            f'<div class="etims-poll-wrapper" data-id="{obj.id}" data-url="{reverse("reports:invoice-status-json", args=[obj.pk])}">'
            f'<span class="status-pending">⏳ System Transmitting...</span></div>'
        )),
    ]

@login_required
@user_passes_test(lambda u: u.is_superuser or u.has_role(*FINANCE), redirect_field_name=None)
def download_invoice_pdf(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    qr_code_base64 = ""
    if invoice.etims_status == "TRANSMITTED":
        qr_code_base64 = generate_etims_qr_code(
            invoice_number=str(invoice.id),
            receipt_number=invoice.etims_receipt_number,
            signature=invoice.etims_signature,
            internal_data=invoice.etims_internal_data
        )

    context = {
        'invoice': invoice,
        'qr_code_base64': qr_code_base64,
        'kra_pin': settings.KRA_TAXPAYER_PIN,
        'kra_branch': settings.KRA_BRANCH_CODE,
    }

    template = get_template('invoices/invoice_pdf.html')
    html_content = template.render(context)
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename="invoice_{invoice.id}.pdf"'

    pisa_status = pisa.CreatePDF(html_content, dest=response)
    if pisa_status.err:
        return HttpResponse('An error occurred during eTIMS PDF processing.', status=500)
    return response

@login_required
def invoice_status_json(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    return JsonResponse({
        "status": invoice.etims_status,
        "download_url": reverse("reports:download-invoice-pdf", args=[invoice.id]) if invoice.etims_status == "TRANSMITTED" else None,
        "error": invoice.etims_error_log if invoice.etims_status == "FAILED" else ""
    })

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
            kind=form.cleaned_data["kind"], 
            report_date=form.cleaned_data["report_date"], 
            requested_by=request.user
        )
        
        # 2. INJECT the import right here inside the function block to prevent circular locks:
        from .tasks import build_report 
        
        result = build_report.delay(run.pk)
        task_id = getattr(result, "id", "") or ""
        if task_id:
            ReportRun.objects.filter(pk=run.pk).update(task_id=str(task_id))
        return redirect("reports:detail", pk=run.pk)
        
    return render(request, "reports/home.html", {
        "form": form, 
        "runs": ReportRun.objects.select_related("requested_by").order_by('-id')[:15]
    })

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
@login_required
@user_passes_test(lambda u: u.is_superuser or u.has_role(*FINANCE), redirect_field_name=None)
def issue_invoice_credit_note(request, invoice_id):
    """
    Creates a matching cancellation credit note record from an existing invoice.
    """
    original = get_object_or_404(Invoice, id=invoice_id, is_credit_note=False)
    
    if original.etims_status != "TRANSMITTED":
        messages.error(request, "Cannot reverse an invoice that hasn't been successfully sent to KRA.")
        return redirect('reports:invoice-list')
        
    # Check if a reversal already exists to prevent duplicate claims
    if Invoice.objects.filter(original_invoice=original, etims_status="TRANSMITTED").exists():
        messages.warning(request, "This transaction has already been reversed.")
        return redirect('reports:invoice-list')

    # Create the Credit Note transaction tracking instance
    credit_note = Invoice.objects.create(
        customer=original.customer,
        total_amount=original.total_amount,
        payment_method_code=original.payment_method_code,
        is_credit_note=True,
        original_invoice=original,
        reversal_reason_code="02", # "02" represents data correction / voiding
        etims_status="PENDING"
    )

    # Replicate invoice lines exactly with matching values
    for line in original.lines.all():
        credit_note.lines.create(
            product=line.product,
            quantity=line.quantity,
            unit_price=line.unit_price,
            subtotal=line.subtotal,
            taxable_amount=line.taxable_amount,
            vat_amount=line.vat_amount,
            total_amount=line.total_amount
        )
        
    messages.success(request, f"Credit Note #{credit_note.id} initialized and queued for KRA transmission.")
    return redirect('reports:invoice-list')
