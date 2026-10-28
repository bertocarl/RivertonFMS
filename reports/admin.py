from django.contrib import admin

from .models import ReportRun


@admin.register(ReportRun)
class ReportRunAdmin(admin.ModelAdmin):
    list_display = ("kind", "report_date", "status", "requested_by", "created_at")
    readonly_fields = ("result",)
