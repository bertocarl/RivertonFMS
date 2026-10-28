from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from forecourt.models import Nozzle, Product, Pump, Station, Tank
from ledger.chart import DEFAULT_CHART
from ledger.models import Account
from purchases.models import Supplier
from sales.models import Customer


class Command(BaseCommand):
    help = "Create the Bonje station, chart of accounts, products, tanks, pumps and nozzles. Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Also create demo users, a supplier, customers and tank stock.")

    @transaction.atomic
    def handle(self, *args, **options):
        station, _ = Station.objects.get_or_create(
            code="BONJE", defaults={"name": "TotalEnergies Bonje", "address": "Bonje, Mombasa", "phone": ""}
        )
        for code, name, kind in DEFAULT_CHART:
            Account.objects.get_or_create(code=code, defaults={"name": name, "type": kind})

        # Prices below are placeholders. Set the current pump prices under Products and prices.
        fuels = {
            "PMS": ("Super Petrol", "190.00", "172.00"),
            "AGO": ("Diesel", "178.00", "162.00"),
            "IK": ("Kerosene", "155.00", "140.00"),
        }
        products = {}
        for code, (name, sell, cost) in fuels.items():
            products[code], _ = Product.objects.get_or_create(
                code=code,
                defaults={"name": name, "kind": "FUEL", "unit": "L", "selling_price": Decimal(sell), "cost_price": Decimal(cost)},
            )
        extras = [
            ("OIL1", "Engine oil 1L", "LUBE", "pc", "950.00", "720.00", 10),
            ("OIL4", "Engine oil 4L", "LUBE", "pc", "3400.00", "2700.00", 5),
            ("LPG6", "LPG 6kg refill", "LPG", "pc", "1250.00", "1050.00", 5),
            ("LPG13", "LPG 13kg refill", "LPG", "pc", "2800.00", "2450.00", 5),
        ]
        for code, name, kind, unit, sell, cost, reorder in extras:
            Product.objects.get_or_create(
                code=code,
                defaults={"name": name, "kind": kind, "unit": unit, "selling_price": Decimal(sell),
                          "cost_price": Decimal(cost), "reorder_level": reorder},
            )

        tank_spec = [("T1", "PMS", 30000, 3000), ("T2", "AGO", 30000, 3000), ("T3", "IK", 10000, 1000)]
        tanks = {}
        for name, code, capacity, minimum in tank_spec:
            tanks[code], _ = Tank.objects.get_or_create(
                station=station, name=name,
                defaults={"product": products[code], "capacity": capacity, "minimum_level": minimum},
            )

        layout = {1: ("PMS", "AGO"), 2: ("PMS", "AGO"), 3: ("PMS", "AGO"), 4: ("PMS", "IK")}
        for number, nozzle_products in layout.items():
            pump, _ = Pump.objects.get_or_create(
                station=station, number=number, defaults={"ifsf_node_id": f"IFSF-BONJE-{number:02d}"}
            )
            for n, code in enumerate(nozzle_products, start=1):
                Nozzle.objects.get_or_create(pump=pump, number=n, defaults={"tank": tanks[code]})

        self.stdout.write(self.style.SUCCESS("Station, chart of accounts, products, tanks and pumps are ready."))

        if options["demo"]:
            self._demo(tanks)

    def _demo(self, tanks):
        User = get_user_model()
        password = "ChangeMe123!"
        for username, role in [("manager", "manager"), ("supervisor", "supervisor"),
                               ("attendant", "attendant"), ("accountant", "accountant")]:
            user, created = User.objects.get_or_create(username=username, defaults={"role": role, "first_name": username.title()})
            if created:
                user.set_password(password)
                user.is_staff = role == "manager"
                user.save()
        for tank in tanks.values():
            if tank.current_level == 0:
                tank.current_level = tank.capacity / 2
                tank.save(update_fields=["current_level"])
        Supplier.objects.get_or_create(name="Demo Fuel Supplier Ltd", defaults={"terms_days": 14})
        Customer.objects.get_or_create(name="Demo Transport Co", defaults={"credit_limit": Decimal("200000")})
        self.stdout.write(self.style.WARNING(
            f"Demo users manager / supervisor / attendant / accountant created with password {password}. Change these before real use."
        ))
