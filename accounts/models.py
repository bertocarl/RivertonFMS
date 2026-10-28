from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ATTENDANT = "attendant", "Pump attendant / cashier"
        SUPERVISOR = "supervisor", "Shift supervisor"
        ACCOUNTANT = "accountant", "Accountant"
        MANAGER = "manager", "Station manager"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ATTENDANT)
    phone = models.CharField(max_length=30, blank=True)

    def has_role(self, *roles) -> bool:
        return self.is_superuser or self.role in roles

    def __str__(self):
        return self.get_full_name() or self.username
