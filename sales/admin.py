from django.contrib import admin

from .models import Customer, CustomerPayment, Invoice, Sale

admin.site.register(Customer)
admin.site.register(Invoice)
admin.site.register(CustomerPayment)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("created_at", "shift", "product", "quantity", "amount", "payment_method")
    list_filter = ("payment_method", "product")
