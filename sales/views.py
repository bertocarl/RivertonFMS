from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html

from common.views import FINANCE, SUPERVISORS, CreateRecord, TableListView, UpdateRecord
from forecourt.models import Product
from shifts.services import get_open_shift

from .forms import CustomerForm, CustomerPaymentForm, SaleForm
from .models import Customer, CustomerPayment, Invoice, Sale
from .services import SaleError, record_customer_payment, record_sale


@login_required
def sale_entry(request):
    """Enter a sale. After saving, a summary appears with a Next button (or press F3)."""
    saved_id = request.GET.get("saved")
    if saved_id:
        sale = get_object_or_404(Sale.objects.select_related("product", "customer", "invoice"), pk=saved_id)
        return render(request, "sales/saved.html", {"sale": sale})

    shift = get_open_shift()
    form = SaleForm(request.POST or None)
    if shift and request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            sale = record_sale(
                shift=shift, product=d["product"], quantity=d["quantity"], unit_price=d["unit_price"],
                payment_method=d["payment_method"], customer=d["customer"], nozzle=d["nozzle"],
                reference=d["reference"], vehicle_reg=d["vehicle_reg"], user=request.user,
            )
        except SaleError as exc:
            form.add_error(None, str(exc))
        else:
            return redirect(f"{reverse('sales:entry')}?saved={sale.pk}")
    return render(request, "sales/entry.html", {"form": form, "shift": shift})


@login_required
def price_field(request):
    """HTMX partial: refill the price box when the product changes."""
    product = Product.objects.filter(pk=request.GET.get("product") or 0).first()
    value = product.selling_price if product else ""
    return HttpResponse(
        format_html(
            '<input type="number" step="0.01" name="unit_price" id="id_unit_price" class="fld" value="{}">', value
        )
    )


class SaleList(TableListView):
    title = "Sales entries"
    model = Sale
    columns = [
        ("Time", "created_at"),
        ("Shift", "shift__code"),
        ("Product", "product__name"),
        ("Qty", "quantity"),
        ("Price", "unit_price"),
        ("Amount", "amount"),
        ("Paid by", "get_payment_method_display"),
        ("Customer", "customer__name"),
        ("Vehicle", "vehicle_reg"),
    ]

    def get_queryset(self):
        qs = Sale.objects.select_related("shift", "product", "customer")
        shift = self.request.GET.get("shift")
        return qs.filter(shift_id=shift) if shift else qs


class CustomerList(TableListView):
    roles = SUPERVISORS + ("accountant",)
    title = "Credit customers"
    model = Customer
    add_url = "sales:customer_add"
    edit_url = "sales:customer_edit"
    columns = [
        ("Customer", "name"),
        ("Phone", "phone"),
        ("Credit limit", "credit_limit"),
        ("Owes", "balance"),
        ("Active", "is_active"),
    ]


class CustomerCreate(CreateRecord):
    roles = FINANCE
    form_class = CustomerForm
    model = Customer
    title = "Add credit customer"
    success_url = reverse_lazy("sales:customers")


class CustomerUpdate(UpdateRecord):
    roles = FINANCE
    form_class = CustomerForm
    model = Customer
    title = "Edit credit customer"
    success_url = reverse_lazy("sales:customers")


class InvoiceList(TableListView):
    roles = SUPERVISORS + ("accountant",)
    title = "Invoices"
    model = Invoice
    columns = [
        ("Invoice", "number"),
        ("Customer", "customer__name"),
        ("Date", "issue_date"),
        ("Total", "total_amount"),
        ("Paid", "amount_paid"),
        ("Balance", "balance"),
        ("Status", "get_status_display"),
    ]

    def get_queryset(self):
        return Invoice.objects.select_related("customer")


class PaymentCreate(CreateRecord):
    roles = FINANCE
    form_class = CustomerPaymentForm
    model = CustomerPayment
    title = "Receive customer payment"
    success_url = reverse_lazy("sales:invoices")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop("instance", None)
        return kwargs

    def form_valid(self, form):
        d = form.cleaned_data
        try:
            record_customer_payment(
                customer=d["customer"], amount=d["amount"], method=d["method"], date=d["date"],
                reference=d["reference"], user=self.request.user,
            )
        except SaleError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Payment recorded and applied to the oldest open invoices.")
        return redirect(self.success_url)
