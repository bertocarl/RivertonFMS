from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum

from common.models import TimeStamped


class Supplier(TimeStamped):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    terms_days = models.PositiveSmallIntegerField("Payment terms (days)", default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    @property
    def balance(self) -> Decimal:
        bought = self.purchases.filter(status="POSTED").aggregate(
            t=Sum("lines__line_total")
        )["t"] or Decimal("0")
        paid = self.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        return bought - paid

    def __str__(self):
        return self.name


class Purchase(TimeStamped):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Received and posted"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    invoice_no = models.CharField("Supplier invoice no.", max_length=40)
    delivery_note = models.CharField(max_length=40, blank=True)
    vehicle_reg = models.CharField("Delivery vehicle", max_length=20, blank=True)
    delivery_date = models.DateField()
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.DRAFT)
    posted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-delivery_date", "-id"]
        unique_together = [("supplier", "invoice_no")]

    @property
    def total(self) -> Decimal:
        return sum((line.line_total for line in self.lines.all()), Decimal("0"))

    def __str__(self):
        return f"{self.supplier} {self.invoice_no}"


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("forecourt.Product", on_delete=models.PROTECT)
    tank = models.ForeignKey("forecourt.Tank", null=True, blank=True, on_delete=models.PROTECT, help_text="Required for fuel.")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.line_total = (self.quantity * self.unit_cost).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


class SupplierPayment(TimeStamped):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        BANK = "BANK", "Bank transfer / cheque"
        MPESA = "MPESA", "M-Pesa"

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payments")
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=5, choices=Method.choices, default=Method.BANK)
    reference = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date", "-id"]
