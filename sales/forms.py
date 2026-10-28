from decimal import Decimal

from django import forms
from django.urls import reverse
from django.utils import timezone

from common.forms import StyledForm, StyledModelForm
from forecourt.models import Nozzle, Product

from .models import Customer, CustomerPayment, Sale


class SaleForm(StyledForm):
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    quantity = forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False, label="Price per unit",
        help_text="Leave empty to use the current pump price.",
    )
    payment_method = forms.ChoiceField(choices=Sale.Method.choices)
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label="Credit customer")
    nozzle = forms.ModelChoiceField(queryset=Nozzle.objects.none(), required=False, label="Pump / nozzle")
    reference = forms.CharField(max_length=60, required=False, label="Card slip or M-Pesa code")
    vehicle_reg = forms.CharField(max_length=20, required=False, label="Vehicle registration")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        self.fields["nozzle"].queryset = Nozzle.objects.filter(is_active=True).select_related("pump", "tank__product")
        self.fields["quantity"].widget.attrs["step"] = "0.001"
        self.fields["product"].widget.attrs.update(
            {"hx-get": reverse("sales:price"), "hx-target": "#price-wrap", "hx-swap": "innerHTML", "autofocus": True}
        )

    def clean(self):
        data = super().clean()
        if data.get("payment_method") == Sale.Method.CREDIT and not data.get("customer"):
            self.add_error("customer", "Choose the credit customer.")
        if data.get("payment_method") in (Sale.Method.CARD, Sale.Method.MPESA) and not data.get("reference"):
            self.add_error("reference", "Enter the slip number or M-Pesa code.")
        return data


class CustomerForm(StyledModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "kra_pin", "credit_limit", "is_active"]


class CustomerPaymentForm(StyledModelForm):
    class Meta:
        model = CustomerPayment
        fields = ["customer", "date", "amount", "method", "reference"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        self.fields["date"].initial = timezone.localdate
