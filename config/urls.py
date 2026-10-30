from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
#from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("forecourt.urls")),
    path("shifts/", include("shifts.urls")),
    path("sales/", include("sales.urls")),
    path("purchases/", include("purchases.urls")),
    path("ledger/", include("ledger.urls")),
    path("reports/", include("reports.urls")),
    # path(
    #     "invoices/<int:invoice_id>/status/", 
    #     views.check_invoice_etims_status, 
    #     name="check-invoice-status"
    # ),
    # path(
    #     "invoices/<int:invoice_id>/pdf/", 
    #     views.download_invoice_pdf, 
    #     name="download-invoice-pdf"
    # ),
    
]
