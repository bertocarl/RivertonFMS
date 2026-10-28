from decimal import Decimal

from django.conf import settings
from django.db import models

from common.models import TimeStamped


class Station(TimeStamped):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)

    def __str__(self):
        return self.name


class Product(TimeStamped):
    class Kind(models.TextChoices):
        FUEL = "FUEL", "Fuel"
        LUBRICANT = "LUBE", "Lubricant"
        LPG = "LPG", "LPG / gas"
        SHOP = "SHOP", "Shop item"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=5, choices=Kind.choices, default=Kind.FUEL)
    unit = models.CharField(max_length=10, default="L")
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Fuel stock lives in tanks. This is the on-hand quantity for everything else.
    stock_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]

    @property
    def is_fuel(self) -> bool:
        return self.kind == self.Kind.FUEL

    def change_price(self, new_price, user=None, effective_from=None):
        from django.utils import timezone

        new_price = Decimal(new_price)
        if new_price == self.selling_price:
            return None
        change = PriceChange.objects.create(
            product=self,
            old_price=self.selling_price,
            new_price=new_price,
            changed_by=user,
            effective_from=effective_from or timezone.now(),
        )
        self.selling_price = new_price
        self.save(update_fields=["selling_price", "updated_at"])
        return change

    def __str__(self):
        return self.name


class PriceChange(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_changes")
    old_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    effective_from = models.DateTimeField()

    class Meta:
        ordering = ["-effective_from"]


class Tank(TimeStamped):
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="tanks")
    name = models.CharField(max_length=40)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, limit_choices_to={"kind": "FUEL"}, related_name="tanks")
    capacity = models.DecimalField(max_digits=12, decimal_places=2)
    minimum_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_level = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("station", "name")]

    @property
    def percent_full(self):
        return round(float(self.current_level) / float(self.capacity) * 100, 1) if self.capacity else 0

    @property
    def is_low(self) -> bool:
        return self.current_level <= self.minimum_level

    def __str__(self):
        return f"{self.name} ({self.product.name})"


class Pump(TimeStamped):
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="pumps")
    number = models.PositiveSmallIntegerField()
    # Address of this dispenser on the IFSF forecourt controller network.
    ifsf_node_id = models.CharField("IFSF node ID", max_length=40, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number"]
        unique_together = [("station", "number")]

    def __str__(self):
        return f"Pump {self.number}"


class Nozzle(TimeStamped):
    pump = models.ForeignKey(Pump, on_delete=models.CASCADE, related_name="nozzles")
    number = models.PositiveSmallIntegerField()
    tank = models.ForeignKey(Tank, on_delete=models.PROTECT, related_name="nozzles")
    # Last totalizer values reported by the pump (or recorded at the last shift close).
    totalizer_volume = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    totalizer_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["pump__number", "number"]
        unique_together = [("pump", "number")]

    @property
    def product(self):
        return self.tank.product

    def __str__(self):
        return f"P{self.pump.number}-N{self.number} {self.tank.product.name}"


class StockMovement(models.Model):
    class Reason(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase / delivery"
        SALE = "SALE", "Counter sale"
        SHIFT_METER = "METER", "Pump meter sales"
        ADJUSTMENT = "ADJ", "Adjustment"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    tank = models.ForeignKey(Tank, null=True, blank=True, on_delete=models.PROTECT, related_name="movements")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)  # signed
    reason = models.CharField(max_length=10, choices=Reason.choices)
    reference = models.CharField(max_length=60, blank=True)
    business_date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-business_date", "-id"]
        indexes = [models.Index(fields=["product", "business_date"])]


class FuellingTransaction(models.Model):
    """Raw dispense events pushed by the pump gateway over the IFSF API."""

    nozzle = models.ForeignKey(Nozzle, on_delete=models.PROTECT, related_name="transactions")
    external_id = models.CharField(max_length=80, blank=True, db_index=True)
    volume = models.DecimalField(max_digits=12, decimal_places=3)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    totalizer_volume = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    totalizer_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    occurred_at = models.DateTimeField()
    shift = models.ForeignKey("shifts.Shift", null=True, blank=True, on_delete=models.SET_NULL, related_name="fuelling")
    raw = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["nozzle", "external_id"],
                condition=~models.Q(external_id=""),
                name="uniq_nozzle_external_id",
            )
        ]
