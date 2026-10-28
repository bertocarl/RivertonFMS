from django import forms
from django.forms import modelformset_factory
from django.utils import timezone

from common.forms import StyledForm, StyledModelForm

from .models import MeterReading


class ReadingForm(StyledModelForm):
    class Meta:
        model = MeterReading
        fields = ["closing_litres", "closing_cash_meter"]

    def clean(self):
        data = super().clean()
        opening = self.instance.opening_litres
        opening_cash = self.instance.opening_cash_meter
        litres, cash = data.get("closing_litres"), data.get("closing_cash_meter")
        if litres is not None and litres < opening:
            self.add_error("closing_litres", f"Must be at least the opening meter ({opening}).")
        if cash is not None and cash < opening_cash:
            self.add_error("closing_cash_meter", f"Must be at least the opening meter ({opening_cash}).")
        if (litres is None) != (cash is None):
            self.add_error(None, "Enter both closing meters for a nozzle, or leave both empty.")
        return data


ReadingFormSet = modelformset_factory(MeterReading, form=ReadingForm, extra=0)


class VerifyForm(StyledForm):
    business_date = forms.DateField(label="Shift date", initial=timezone.localdate)
    accept_variance = forms.BooleanField(
        label="I accept the shortage or meter difference shown above", required=False
    )


def dip_form_class(tanks, initial=None):
    """Build a form with one litres field per tank."""
    initial = initial or {}
    fields = {
        f"tank_{t.pk}": forms.DecimalField(
            label=f"{t.name} ({t.product.name}) litres",
            max_digits=14,
            decimal_places=2,
            min_value=0,
            required=False,
            initial=initial.get(t.pk),
        )
        for t in tanks
    }
    return type("DipForm", (StyledForm,), fields)
