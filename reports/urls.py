from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_home, name="home"),
    path("<int:pk>/", views.report_detail, name="detail"),
    path("<int:pk>/body/", views.report_body, name="body"),
    path("<int:pk>/pdf/", views.report_pdf, name="pdf"),
    path("invoices/", views.InvoiceListView.as_view(), name="invoice-list"),
    path("invoices/<int:invoice_id>/json/", views.invoice_status_json, name="invoice-status-json"),
    path("invoices/<int:invoice_id>/pdf/", views.download_invoice_pdf, name="download-invoice-pdf"),
]
