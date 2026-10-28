from django.urls import path

from . import views

app_name = "ledger"

urlpatterns = [
    path("accounts/", views.AccountList.as_view(), name="accounts"),
    path("journal/", views.JournalList.as_view(), name="journal"),
    path("expenses/", views.ExpenseList.as_view(), name="expenses"),
    path("expenses/add/", views.ExpenseCreate.as_view(), name="expense_add"),
]
