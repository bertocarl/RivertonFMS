from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DetailView

from common.views import FINANCE, CreateRecord, RoleMixin, TableListView

from .forms import ExpenseForm
from .models import Account, Expense, JournalEntry
from .services import post_expense


class AccountList(TableListView):
    roles = FINANCE
    title = "Chart of accounts"
    model = Account
    columns = [("Code", "code"), ("Account", "name"), ("Type", "get_type_display"), ("Active", "is_active")]


class JournalList(TableListView):
    roles = FINANCE
    title = "Journal entries"
    model = JournalEntry
    columns = [
        ("No.", lambda e: f"JE{e.pk:06d}"),
        ("Date", "date"),
        ("Memo", "memo"),
        ("Source", "source"),
        ("Amount", lambda e: e.total),
    ]

    def get_queryset(self):
        return JournalEntry.objects.prefetch_related("lines")


class ExpenseList(TableListView):
    roles = FINANCE
    title = "Expenses"
    model = Expense
    add_url = "ledger:expense_add"
    add_label = "Record expense"
    columns = [
        ("Date", "date"),
        ("Account", "account__name"),
        ("Description", "description"),
        ("Paid from", "get_paid_from_display"),
        ("Reference", "reference"),
        ("Amount", "amount"),
    ]


class ExpenseCreate(CreateRecord):
    roles = FINANCE
    form_class = ExpenseForm
    model = Expense
    title = "Record expense"
    success_url = reverse_lazy("ledger:expenses")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        post_expense(self.object, self.request.user)
        return response
