from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from common.views import FINANCE, SUPERVISORS, CreateRecord, TableListView, UpdateRecord

from .forms import PurchaseForm, PurchaseLineFormSet, SupplierForm, SupplierPaymentForm
from .models import Purchase, Supplier, SupplierPayment
from .services import PurchaseError, pay_supplier, post_purchase

BUYERS = SUPERVISORS + ("accountant",)


class PurchaseList(TableListView):
    roles = BUYERS
    title = "Purchases and deliveries"
    model = Purchase
    add_url = "purchases:add"
    add_label = "Record delivery"
    columns = [
        ("Delivery date", "delivery_date"),
        ("Supplier", "supplier__name"),
        ("Invoice no.", "invoice_no"),
        ("Vehicle", "vehicle_reg"),
        ("Total", "total"),
        ("Status", "get_status_display"),
    ]

    def get_queryset(self):
        return Purchase.objects.select_related("supplier").prefetch_related("lines")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for row, purchase in zip(ctx["rows"], ctx["object_list"]):
            row["open_url"] = purchase.pk
        return ctx


@login_required
def purchase_add(request):
    if not request.user.has_role(*BUYERS):
        raise PermissionDenied
    form = PurchaseForm(request.POST or None)
    formset = PurchaseLineFormSet(request.POST or None, instance=Purchase())
    if request.method == "POST" and form.is_valid():
        purchase = form.save(commit=False)
        purchase.created_by = request.user
        formset = PurchaseLineFormSet(request.POST, instance=purchase)
        if formset.is_valid():
            filled = [f for f in formset.forms if f.has_changed()]
            if not filled:
                form.add_error(None, "Add at least one product line.")
            else:
                purchase.save()
                formset.instance = purchase
                formset.save()
                messages.success(request, "Delivery saved as a draft. Review it, then post it to update stock.")
                return redirect("purchases:detail", pk=purchase.pk)
    return render(request, "purchases/form.html", {"form": form, "formset": formset})


@login_required
def purchase_detail(request, pk):
    if not request.user.has_role(*BUYERS):
        raise PermissionDenied
    purchase = get_object_or_404(Purchase.objects.select_related("supplier"), pk=pk)
    return render(request, "purchases/detail.html", {"purchase": purchase, "lines": purchase.lines.select_related("product", "tank")})


@login_required
@require_POST
def purchase_post(request, pk):
    if not request.user.has_role(*BUYERS):
        raise PermissionDenied
    purchase = get_object_or_404(Purchase, pk=pk)
    try:
        post_purchase(purchase, request.user)
    except Exception as exc:  # PurchaseError / StockError / LedgerError
        messages.error(request, str(exc))
    else:
        messages.success(request, "Posted. Stock and the supplier balance are updated.")
    return redirect("purchases:detail", pk=pk)


class SupplierList(TableListView):
    roles = BUYERS
    title = "Suppliers"
    model = Supplier
    add_url = "purchases:supplier_add"
    edit_url = "purchases:supplier_edit"
    columns = [("Supplier", "name"), ("Phone", "phone"), ("Terms (days)", "terms_days"), ("We owe", "balance"), ("Active", "is_active")]


class SupplierCreate(CreateRecord):
    roles = FINANCE
    form_class = SupplierForm
    model = Supplier
    title = "Add supplier"
    success_url = reverse_lazy("purchases:suppliers")


class SupplierUpdate(UpdateRecord):
    roles = FINANCE
    form_class = SupplierForm
    model = Supplier
    title = "Edit supplier"
    success_url = reverse_lazy("purchases:suppliers")


class SupplierPaymentCreate(CreateRecord):
    roles = FINANCE
    form_class = SupplierPaymentForm
    model = SupplierPayment
    title = "Pay supplier"
    success_url = reverse_lazy("purchases:suppliers")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop("instance", None)
        return kwargs

    def form_valid(self, form):
        d = form.cleaned_data
        try:
            pay_supplier(
                supplier=d["supplier"], amount=d["amount"], method=d["method"], date=d["date"],
                reference=d["reference"], user=self.request.user,
            )
        except PurchaseError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Payment recorded.")
        return redirect(self.success_url)
