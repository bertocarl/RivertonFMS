from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.urls import reverse
from django.views.generic import CreateView, ListView, UpdateView
from xhtml2pdf import pisa

from .models import Invoice
from .utils import fmt, generate_etims_qr_code

# Role groups used across the project
MANAGERS = ("manager",)
SUPERVISORS = ("supervisor", "manager")
FINANCE = ("accountant", "manager")
ANYONE_OPS = ("attendant", "supervisor", "accountant", "manager")


class RoleMixin(LoginRequiredMixin, UserPassesTestMixin):
    """roles=None means any signed-in user. Superusers always pass."""

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
    columns = []  # Expected format: [("Header Label", "attr__path" | callable)]
    add_url = None
    add_label = "Add"
    edit_url = None
    paginate_by = 50

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title
        
        # 1. Correctly unpack the header text from your tuple list
        ctx["headers"] = [c[0] for c in self.columns]
        ctx["add_url"] = reverse(self.add_url) if self.add_url else None
        ctx["add_label"] = self.add_label
        
        # 2. Fix the cell indexing assignment to explicitly pass c[1] to render_cell
        ctx["rows"] = [
            {
                "cells": [render_cell(obj, c[1]) for c in self.columns],
                "edit": reverse(self.edit_url, args=[obj.pk]) if self.edit_url else None,
            }
            for obj in ctx["object_list"]
        ]
        return ctx


class SaveMixin:
    template_name = "generic/form.html"
    title = ""
    success_message = "Saved."

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title
        ctx["cancel_url"] = str(self.success_url)
        return ctx


class CreateRecord(SaveMixin, RoleMixin, CreateView):
    pass


class UpdateRecord(SaveMixin, RoleMixin, UpdateView):
    pass


# --- Fixed & Secured eTIMS View ---
@login_required
@user_passes_test(lambda u: u.is_superuser or u.has_role(*FINANCE), redirect_field_name=None)
def download_invoice_pdf(request, invoice_id):
    """
    Renders an invoice layout to PDF using xhtml2pdf, injecting the
    statutory KRA eTIMS payload details and compliance QR matrix.
    """
    # 1. Fetch the invoice record from your running database
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    # 2. Generate the compliant Base64 QR code image string
    qr_code_base64 = ""
    if invoice.etims_status == "TRANSMITTED":
        qr_code_base64 = generate_etims_qr_code(
            invoice_number=str(invoice.id),
            receipt_number=invoice.etims_receipt_number,
            signature=invoice.etims_signature,
            internal_data=invoice.etims_internal_data
        )

    # 3. Compile context payload for the layout engine
    context = {
        'invoice': invoice,
        'qr_code_base64': qr_code_base64,
        'kra_pin': settings.KRA_TAXPAYER_PIN,
        'kra_branch': settings.KRA_BRANCH_CODE,
    }

    # 4. Fetch the target HTML invoice template
    template = get_template('invoices/invoice_pdf.html')
    html_content = template.render(context)
    
    # 5. Initialize the response stream with proper content types
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename="invoice_{invoice.id}.pdf"'

    # 6. Parse the HTML code into a binary document using pisa
    pisa_status = pisa.CreatePDF(html_content, dest=response)
    
    # Return the file response if no generation errors occur
    if pisa_status.err:
        return HttpResponse('An error occurred during eTIMS PDF processing.', status=500)
        
    return response

def check_invoice_etims_status(request, invoice_id):
    """
    Returns a small HTML fragment representing the up-to-date eTIMS button status.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id)
    
    if invoice.etims_status == "TRANSMITTED":
        download_url = reverse("download-invoice-pdf", args=[invoice.id])
        return HttpResponse(
            f'<a href="{download_url}" class="btn-pdf-download" target="_blank">📄 Download PDF</a>'
        )
    elif invoice.etims_status == "FAILED":
        return HttpResponse(
            f'<span class="status-failed" title="{invoice.etims_error_log or "Unknown Error"}">❌ Transmission Failed</span>'
        )
    else:
        # PENDING status: Keep polling every 3 seconds until status shifts from pending
        poll_url = reverse("check-invoice-status", args=[invoice.id])
        return HttpResponse(
            f'<span hx-get="{poll_url}" hx-trigger="every 3s" hx-swap="outerHTML" class="status-pending">'
            f'⏳ Processing eTIMS...</span>'
        )
