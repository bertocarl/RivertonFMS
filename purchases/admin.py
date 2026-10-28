from django.contrib import admin

from .models import Purchase, PurchaseLine, Supplier, SupplierPayment


class LineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("delivery_date", "supplier", "invoice_no", "status")
    inlines = [LineInline]


admin.site.register(Supplier)
admin.site.register(SupplierPayment)
