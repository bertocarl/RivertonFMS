from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStamped


class Shift(TimeStamped):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        VERIFIED = "VERIFIED", "Verified"
        CLOSED = "CLOSED", "Closed"

    station = models.ForeignKey("forecourt.Station", on_delete=models.PROTECT, related_name="shifts")
    code = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts_opened")
    opened_at = models.DateTimeField(default=timezone.now)
    business_date = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="shifts_verified"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    variance_accepted = models.BooleanField(default=False)
    backed_up_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="shifts_closed"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    @property
    def is_open(self) -> bool:
        return self.status == self.Status.OPEN

    def __str__(self):
        return self.code


class MeterReading(models.Model):
    """Opening and closing pump meters for one nozzle in one shift."""

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="readings")
    nozzle = models.ForeignKey("forecourt.Nozzle", on_delete=models.PROTECT, related_name="readings")
    opening_litres = models.DecimalField(max_digits=16, decimal_places=2)
    closing_litres = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    opening_cash_meter = models.DecimalField("opening electric cash", max_digits=16, decimal_places=2)
    closing_cash_meter = models.DecimalField("closing electric cash", max_digits=16, decimal_places=2, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["nozzle__pump__number", "nozzle__number"]
        unique_together = [("shift", "nozzle")]

    @property
    def is_complete(self) -> bool:
        return self.closing_litres is not None and self.closing_cash_meter is not None

    @property
    def litres_sold(self) -> Decimal:
        if self.closing_litres is None:
            return Decimal("0")
        return self.closing_litres - self.opening_litres

    @property
    def electric_cash(self) -> Decimal:
        if self.closing_cash_meter is None:
            return Decimal("0")
        return self.closing_cash_meter - self.opening_cash_meter

    @property
    def expected_value(self) -> Decimal:
        return (self.litres_sold * self.unit_price).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.shift} {self.nozzle}"


class TankDip(models.Model):
    class Phase(models.TextChoices):
        OPEN = "OPEN", "Opening dip"
        CLOSE = "CLOSE", "Closing dip"

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="dips")
    tank = models.ForeignKey("forecourt.Tank", on_delete=models.PROTECT, related_name="dips")
    phase = models.CharField(max_length=5, choices=Phase.choices)
    litres = models.DecimalField(max_digits=14, decimal_places=2)
    measured_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    measured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("shift", "tank", "phase")]
