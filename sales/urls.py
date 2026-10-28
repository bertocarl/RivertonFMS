from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("", views.SaleList.as_view(), name="list"),
    path("entry/", views.sale_entry, name="entry"),
    path("entry/price/", views.price_field, name="price"),
    path("customers/", views.CustomerList.as_view(), name="customers"),
    path("customers/add/", views.CustomerCreate.as_view(), name="customer_add"),
    path("customers/<int:pk>/", views.CustomerUpdate.as_view(), name="customer_edit"),
    path("invoices/", views.InvoiceList.as_view(), name="invoices"),
    path("payments/add/", views.PaymentCreate.as_view(), name="payment_add"),
]
