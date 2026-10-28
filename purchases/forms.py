from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from common.forms import StyledModelForm

from .models import Purchase, PurchaseLine, Supplier, SupplierPayment


class PurchaseForm(StyledModelForm):
    class Meta:
        model = Purchase
        fields = ["supplier", "invoice_no", "delivery_note", "vehicle_reg", "delivery_date"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["delivery_date"].initial = timezone.localdate


class PurchaseLineForm(StyledModelForm):
    class Meta:
        model = PurchaseLine
        fields = ["product", "tank", "quantity", "unit_cost"]

    def clean(self):
        data = super().clean()
        product, tank = data.get("product"), data.get("tank")
        if product and product.is_fuel and not tank:
            self.add_error("tank", "Choose the tank this fuel goes into.")
        if product and tank and tank.product_id != product.pk:
            self.add_error("tank", f"{tank.name} holds {tank.product.name}, not {product.name}.")
        return data


PurchaseLineFormSet = inlineformset_factory(
    Purchase, PurchaseLine, form=PurchaseLineForm, extra=4, can_delete=False
)


class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "phone", "kra_pin", "terms_days", "is_active"]


class SupplierPaymentForm(StyledModelForm):
    class Meta:
        model = SupplierPayment
        fields = ["supplier", "date", "amount", "method", "reference"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["date"].initial = timezone.localdate
