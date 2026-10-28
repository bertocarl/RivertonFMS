from django.contrib import admin

from .models import MeterReading, Shift, TankDip


class ReadingInline(admin.TabularInline):
    model = MeterReading
    extra = 0


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("code", "status", "business_date", "opened_by", "backed_up_at")
    list_filter = ("status",)
    inlines = [ReadingInline]


admin.site.register(TankDip)
