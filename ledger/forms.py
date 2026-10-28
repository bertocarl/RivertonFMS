from django import forms

from common.forms import StyledModelForm

from .models import Account, Expense


class ExpenseForm(StyledModelForm):
    class Meta:
        model = Expense
        fields = ["date", "account", "description", "amount", "paid_from", "reference"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(type="EXPENSE", is_active=True)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount
