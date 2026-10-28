from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_home, name="home"),
    path("<int:pk>/", views.report_detail, name="detail"),
    path("<int:pk>/body/", views.report_body, name="body"),
    path("<int:pk>/pdf/", views.report_pdf, name="pdf"),
]
