from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum

from common.models import TimeStamped


class Customer(TimeStamped):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0, help_text="0 means no limit.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    @property
    def invoiced(self) -> Decimal:
        return self.invoices.aggregate(t=Sum("total_amount"))["t"] or Decimal("0")

    @property
    def paid(self) -> Decimal:
        return self.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def balance(self) -> Decimal:
        return self.invoiced - self.paid

    def __str__(self):
        return self.name


class Invoice(TimeStamped):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PAID = "PAID", "Paid"

    number = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=5, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["-issue_date", "-id"]

    @property
    def balance(self) -> Decimal:
        return self.total_amount - self.amount_paid

    def save(self, *args, **kwargs):
        creating = not self.number
        super().save(*args, **kwargs)
        if creating:
            self.number = f"INV-{self.pk:06d}"
            super().save(update_fields=["number"])

    def __str__(self):
        return self.number


class Sale(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        MPESA = "MPESA", "M-Pesa"
        CARD = "CARD", "Credit / debit card"
        CREDIT = "CREDIT", "Credit account (invoice)"

    shift = models.ForeignKey("shifts.Shift", on_delete=models.PROTECT, related_name="sales")
    product = models.ForeignKey("forecourt.Product", on_delete=models.PROTECT, related_name="sales")
    nozzle = models.ForeignKey("forecourt.Nozzle", null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=6, choices=Method.choices)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    reference = models.CharField("Slip / M-Pesa code", max_length=60, blank=True)
    vehicle_reg = models.CharField("Vehicle registration", max_length=20, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["shift", "payment_method"])]


class CustomerPayment(TimeStamped):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        BANK = "BANK", "Bank transfer / cheque"
        MPESA = "MPESA", "M-Pesa"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=5, choices=Method.choices, default=Method.CASH)
    reference = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date", "-id"]
