from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("", views.PurchaseList.as_view(), name="list"),
    path("add/", views.purchase_add, name="add"),
    path("<int:pk>/", views.purchase_detail, name="detail"),
    path("<int:pk>/post/", views.purchase_post, name="post"),
    path("suppliers/", views.SupplierList.as_view(), name="suppliers"),
    path("suppliers/add/", views.SupplierCreate.as_view(), name="supplier_add"),
    path("suppliers/<int:pk>/", views.SupplierUpdate.as_view(), name="supplier_edit"),
    path("payments/add/", views.SupplierPaymentCreate.as_view(), name="payment_add"),
]
