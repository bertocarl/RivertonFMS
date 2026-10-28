from django.conf import settings
from django.db import models

from .pagination import paginate

class Invoice(models.Model):
    # Existing fields
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # --- eTIMS Specific Fields ---
    etims_receipt_number = models.CharField(max_length=100, blank=True, null=True, unique=True)
    etims_signature = models.TextField(blank=True, null=True)
    etims_internal_data = models.TextField(blank=True, null=True)
    etims_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("TRANSMITTED", "Transmitted Successfully"),
            ("FAILED", "Failed"),
        ],
        default="PENDING",
    )
    etims_error_log = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Invoice #{self.id}"
    
class ReportRun(models.Model):
    class Kind(models.TextChoices):
        DSSR = "DSSR", "Daily station sales report (DSSR)"
        TRIAL = "TRIAL", "Trial balance"
        DEBTORS = "DEBTORS", "Credit customers (debtors)"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Queued"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Ready"
        FAILED = "FAILED", "Failed"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    report_date = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    task_id = models.CharField(max_length=60, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_finished(self) -> bool:
        return self.status in (self.Status.DONE, self.Status.FAILED)

    @property
    def pages(self):
        return paginate(self.result) if self.result else []

    def __str__(self):
        return f"{self.get_kind_display()} {self.report_date:%d/%m/%Y}"
