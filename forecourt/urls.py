from django.urls import path

from . import api, views

app_name = "forecourt"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("products/", views.ProductList.as_view(), name="products"),
    path("products/add/", views.ProductCreate.as_view(), name="product_add"),
    path("products/<int:pk>/", views.ProductUpdate.as_view(), name="product_edit"),
    path("tanks/", views.TankList.as_view(), name="tanks"),
    path("tanks/add/", views.TankCreate.as_view(), name="tank_add"),
    path("tanks/<int:pk>/", views.TankUpdate.as_view(), name="tank_edit"),
    path("pumps/", views.PumpList.as_view(), name="pumps"),
    path("pumps/add/", views.PumpCreate.as_view(), name="pump_add"),
    path("pumps/<int:pk>/", views.PumpUpdate.as_view(), name="pump_edit"),
    path("nozzles/", views.NozzleList.as_view(), name="nozzles"),
    path("nozzles/add/", views.NozzleCreate.as_view(), name="nozzle_add"),
    path("nozzles/<int:pk>/", views.NozzleUpdate.as_view(), name="nozzle_edit"),
    path("api/ifsf/nodes/", api.nodes, name="ifsf_nodes"),
    path("api/ifsf/transaction/", api.transaction_in, name="ifsf_transaction"),
]
