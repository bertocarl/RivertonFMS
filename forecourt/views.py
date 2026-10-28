from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone

from common.views import MANAGERS, SUPERVISORS, CreateRecord, TableListView, UpdateRecord

from .forms import NozzleForm, ProductForm, PumpForm, TankForm
from .models import Nozzle, Product, Pump, Tank


@login_required
def dashboard(request):
    from ledger.services import receivables_total
    from sales.models import Sale
    from shifts.models import Shift

    today = timezone.localdate()
    zero = Value(Decimal("0"), output_field=DecimalField())
    todays_sales = (
        Sale.objects.filter(created_at__date=today)
        .values("payment_method")
        .annotate(total=Coalesce(Sum("amount"), zero))
    )
    by_method = {row["payment_method"]: row["total"] for row in todays_sales}
    fuel_today = (
        Sale.objects.filter(created_at__date=today, product__kind="FUEL")
        .values("product__name")
        .annotate(litres=Coalesce(Sum("quantity"), zero), value=Coalesce(Sum("amount"), zero))
        .order_by("product__name")
    )
    tanks = Tank.objects.filter(is_active=True).select_related("product")
    low_items = Product.objects.filter(is_active=True, kind__in=["LUBE", "LPG", "SHOP"], stock_qty__lte=F("reorder_level"))
    return render(
        request,
        "forecourt/dashboard.html",
        {
            "today": today,
            "total_today": sum(by_method.values(), Decimal("0")),
            "by_method": by_method,
            "fuel_today": fuel_today,
            "tanks": tanks,
            "low_items": low_items,
            "receivables": receivables_total(),
            "recent_shifts": Shift.objects.select_related("opened_by")[:5],
        },
    )


class ProductList(TableListView):
    roles = SUPERVISORS + ("accountant",)
    title = "Products and prices"
    model = Product
    add_url = "forecourt:product_add"
    edit_url = "forecourt:product_edit"
    columns = [
        ("Code", "code"),
        ("Product", "name"),
        ("Type", "get_kind_display"),
        ("Selling price", "selling_price"),
        ("Cost price", "cost_price"),
        ("Stock (non-fuel)", lambda p: "—" if p.is_fuel else p.stock_qty),
        ("Active", "is_active"),
    ]


class ProductCreate(CreateRecord):
    roles = MANAGERS
    form_class = ProductForm
    model = Product
    title = "Add product"
    success_url = reverse_lazy("forecourt:products")


class ProductUpdate(UpdateRecord):
    roles = MANAGERS
    form_class = ProductForm
    model = Product
    title = "Edit product"
    success_url = reverse_lazy("forecourt:products")

    def form_valid(self, form):
        # Route price edits through change_price so the history stays complete.
        old_price = Product.objects.get(pk=self.object.pk).selling_price
        new_price = form.cleaned_data["selling_price"]
        form.instance.selling_price = old_price
        response = super().form_valid(form)
        self.object.change_price(new_price, user=self.request.user)
        return response


class TankList(TableListView):
    roles = SUPERVISORS + ("accountant",)
    title = "Tanks"
    model = Tank
    add_url = "forecourt:tank_add"
    edit_url = "forecourt:tank_edit"
    columns = [
        ("Tank", "name"),
        ("Product", "product__name"),
        ("Capacity (L)", "capacity"),
        ("Current level (L)", "current_level"),
        ("Full", lambda t: f"{t.percent_full}%"),
        ("Low alert at (L)", "minimum_level"),
    ]


class TankCreate(CreateRecord):
    roles = MANAGERS
    form_class = TankForm
    model = Tank
    title = "Add tank"
    success_url = reverse_lazy("forecourt:tanks")


class TankUpdate(UpdateRecord):
    roles = MANAGERS
    form_class = TankForm
    model = Tank
    title = "Edit tank"
    success_url = reverse_lazy("forecourt:tanks")


class PumpList(TableListView):
    roles = SUPERVISORS + ("accountant",)
    title = "Pumps and IFSF nodes"
    model = Pump
    add_url = "forecourt:pump_add"
    edit_url = "forecourt:pump_edit"
    columns = [
        ("Pump", "number"),
        ("IFSF node ID", "ifsf_node_id"),
        ("Nozzles", lambda p: ", ".join(str(n) for n in p.nozzles.all()) or "—"),
        ("Active", "is_active"),
    ]


class PumpCreate(CreateRecord):
    roles = MANAGERS
    form_class = PumpForm
    model = Pump
    title = "Add pump"
    success_url = reverse_lazy("forecourt:pumps")


class PumpUpdate(UpdateRecord):
    roles = MANAGERS
    form_class = PumpForm
    model = Pump
    title = "Edit pump"
    success_url = reverse_lazy("forecourt:pumps")


class NozzleList(TableListView):
    roles = SUPERVISORS + ("accountant",)
    title = "Nozzles"
    model = Nozzle
    add_url = "forecourt:nozzle_add"
    edit_url = "forecourt:nozzle_edit"
    columns = [
        ("Pump", "pump"),
        ("Nozzle", "number"),
        ("Tank", "tank"),
        ("Totalizer (L)", "totalizer_volume"),
        ("Totalizer (KES)", "totalizer_amount"),
        ("Active", "is_active"),
    ]


class NozzleCreate(CreateRecord):
    roles = MANAGERS
    form_class = NozzleForm
    model = Nozzle
    title = "Add nozzle"
    success_url = reverse_lazy("forecourt:nozzles")


class NozzleUpdate(UpdateRecord):
    roles = MANAGERS
    form_class = NozzleForm
    model = Nozzle
    title = "Edit nozzle"
    success_url = reverse_lazy("forecourt:nozzles")
