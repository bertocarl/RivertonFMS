from django.conf import settings
from django.db import models

from common.models import TimeStamped


class Account(TimeStamped):
    class Type(models.TextChoices):
        ASSET = "ASSET", "Asset"
        LIABILITY = "LIABILITY", "Liability"
        EQUITY = "EQUITY", "Equity"
        INCOME = "INCOME", "Income"
        EXPENSE = "EXPENSE", "Expense"

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=Type.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    @property
    def is_debit_normal(self) -> bool:
        return self.type in (self.Type.ASSET, self.Type.EXPENSE)

    def __str__(self):
        return f"{self.code} {self.name}"


class JournalEntry(TimeStamped):
    date = models.DateField()
    memo = models.CharField(max_length=200)
    source = models.CharField(max_length=60, blank=True, help_text="Where this came from, e.g. sales.Sale:42")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "journal entries"

    @property
    def total(self):
        return sum(line.debit for line in self.lines.all())

    def __str__(self):
        return f"JE{self.pk:06d} {self.memo}"


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    narration = models.CharField(max_length=200, blank=True)


class Expense(TimeStamped):
    class PaidFrom(models.TextChoices):
        CASH = "CASH", "Cash on hand"
        BANK = "BANK", "Bank"
        MPESA = "MPESA", "M-Pesa"

    date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, limit_choices_to={"type": "EXPENSE"})
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_from = models.CharField(max_length=5, choices=PaidFrom.choices, default=PaidFrom.CASH)
    reference = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    journal = models.OneToOneField(JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, editable=False)

    class Meta:
        ordering = ["-date", "-id"]
