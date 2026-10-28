from django.contrib import admin

from .models import FuellingTransaction, Nozzle, PriceChange, Product, Pump, Station, StockMovement, Tank

admin.site.register(Station)
admin.site.register(PriceChange)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "selling_price", "cost_price", "stock_qty", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("code", "name")


@admin.register(Tank)
class TankAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "capacity", "current_level", "minimum_level")


@admin.register(Pump)
class PumpAdmin(admin.ModelAdmin):
    list_display = ("number", "ifsf_node_id", "is_active")


@admin.register(Nozzle)
class NozzleAdmin(admin.ModelAdmin):
    list_display = ("pump", "number", "tank", "totalizer_volume", "is_active")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("business_date", "product", "tank", "quantity", "reason", "reference")
    list_filter = ("reason", "product")


@admin.register(FuellingTransaction)
class FuellingTransactionAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "nozzle", "volume", "amount", "shift")
    list_filter = ("nozzle__pump",)
