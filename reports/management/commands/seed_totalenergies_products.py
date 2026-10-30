from django.core.management.base import BaseCommand
from decimal import Decimal
from django.apps import apps

class Command(BaseCommand):
    help = "Safely handles TotalEnergies product transition resolving UNIQUE constraint conflicts by re-linking related models."

    def handle(self, *args, **options):
        # Dynamically pull models to make sure we don't hit import loop bugs
        Product = apps.get_model('forecourt', 'Product')
        Tank = apps.get_model('forecourt', 'Tank')

        # 1. Define the fresh TotalEnergies catalog items
        catalog_products = [
            {"code": "TOT-EXC-PMS", "name": "Total Excellium Premium Petrol (PMS)", "kind": "Fuel", "selling_price": Decimal("190.00")},
            {"code": "TOT-EXC-AGO", "name": "Total Excellium Diesel (AGO)", "kind": "Fuel", "selling_price": Decimal("178.00")},
            {"code": "TOT-EXC-IK", "name": "Total Illuminating Kerosene (IK)", "kind": "Fuel", "selling_price": Decimal("155.00")},
            {"code": "TOT-GAS-3KG-REFILL", "name": "TotalGas 3Kg Refill", "kind": "LPG / gas", "selling_price": Decimal("700.00")},
            {"code": "TOT-GAS-6KG-REFILL", "name": "TotalGas 6Kg Refill", "kind": "LPG / gas", "selling_price": Decimal("1250.00")},
            {"code": "TOT-GAS-13KG-REFILL", "name": "TotalGas 13Kg Refill", "kind": "LPG / gas", "selling_price": Decimal("2800.00")},
            {"code": "TOT-GAS-22.5KG-REFILL", "name": "TotalGas 22.5Kg Refill", "kind": "LPG / gas", "selling_price": Decimal("5500.00")},
            {"code": "TOT-GAS-50KG-REFILL", "name": "TotalGas 50Kg Refill", "kind": "LPG / gas", "selling_price": Decimal("11000.00")},
            {"code": "TOT-LUB-Q9000-5W40-4L", "name": "Total Quartz 9000 Energy 5W-40 (4 Litres)", "kind": "Lubricant", "selling_price": Decimal("5200.00")},
            {"code": "TOT-LUB-Q7000-10W40-4L", "name": "Total Quartz 7000 10W-40 (4 Litres)", "kind": "Lubricant", "selling_price": Decimal("3800.00")},
            {"code": "TOT-LUB-Q5000-20W50-4L", "name": "Total Quartz 5000 20W-50 Premium Mineral (4L)", "kind": "Lubricant", "selling_price": Decimal("2600.00")},
            {"code": "TOT-LUB-HP4T-20W50-1L", "name": "Total Hi-Perf 4T Special Motorcycle Oil (1L)", "kind": "Lubricant", "selling_price": Decimal("950.00")},
            {"code": "TOT-LUB-ATF-FLUIDMATIC-1L", "name": "Total Fluidmatic DII / ATF Transmission Fluid (1L)", "kind": "Lubricant", "selling_price": Decimal("900.00")},
            {"code": "TOT-LUB-CLASSIC-GREASE-1KG", "name": "Total Classic Lithium Multi-Purpose Grease (1Kg)", "kind": "Lubricant", "selling_price": Decimal("1100.00")},
        ]

        # 2. Seed or update all the true TotalEnergies target entries first
        self.stdout.write("Ensuring all new TotalEnergies target items exist...")
        seeded_map = {}
        for item in catalog_products:
            product, _ = Product.objects.update_or_create(
                code=item["code"],
                defaults={
                    "name": item["name"],
                    "kind": item["kind"],
                    "selling_price": item["selling_price"],
                    "is_active": True
                }
            )
            seeded_map[item["code"]] = product

        self.stdout.write(self.style.SUCCESS("TotalEnergies master catalog items synced successfully."))
        self.stdout.write("--------------------------------------------------")

        # 3. Resolve conflicts by moving Tank relations from legacy keys to new codes
        repurpose_rules = {
            "AGO": "TOT-EXC-AGO",
            "IK": "TOT-EXC-IK",
            "PMS": "TOT-EXC-PMS",
        }

        self.stdout.write("Checking and resolving tank unique relation constraint conflicts...")
        for old_code, new_code in repurpose_rules.items():
            old_product = Product.objects.filter(code=old_code).first()
            new_product = seeded_map.get(new_code)

            if old_product and new_product:
                # Safely shift any linked tanks from the old product item to the new item instance
                linked_tanks = Tank.objects.filter(product=old_product)
                tank_count = linked_tanks.count()
                if tank_count > 0:
                    linked_tanks.update(product=new_product)
                    self.stdout.write(self.style.SUCCESS(f"Re-linked {tank_count} tanks from old code '{old_code}' to new code '{new_code}'."))

                # Now that relations are shifted, safely remove or archive the old duplicate record
                old_product.delete()
                self.stdout.write(self.style.WARNING(f"Cleaned up redundant legacy code duplicate entry: '{old_code}'"))

        # 4. Deactivate any remaining unused text codes (LPG13, LPG6, OIL1, OIL4)
        other_legacy_codes = ["LPG13", "LPG6", "OIL1", "OIL4"]
        for old_code in other_legacy_codes:
            Product.objects.filter(code=old_code).update(is_active=False)

        self.stdout.write(self.style.SUCCESS("\nOperation Successful! UNIQUE constraint errors resolved cleanly."))
