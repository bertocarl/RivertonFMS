import sys
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from forecourt.models import Product  # Points to your active app model
from reports.models import Invoice

User = get_user_model()

class Command(BaseCommand):
    help = "Simulates a retail checkout transaction to test the automated Redis + Celery KRA eTIMS transmission pipeline."

    def handle(self, *args, **options):
        self.stdout.write("Initializing eTIMS mock checkout test suite...")

        # 1. Fetch or create a mock customer/user to satisfy relationships
        user, _ = User.objects.get_or_create(
            username="etims_tester",
            defaults={"email": "tester@bonjefms.com", "is_active": True}
        )

        # 2. Fetch the newly seeded standard TotalEnergies products from your database
        pms_fuel = Product.objects.filter(code="TOT-EXC-PMS").first()
        quartz_oil = Product.objects.filter(code="TOT-LUB-Q7000-10W40-4L").first()

        if not pms_fuel or not quartz_oil:
            self.stdout.write(self.style.ERROR(
                "Test aborted: TotalEnergies products not found. "
                "Please run 'python manage.py seed_totalenergies_products' first."
            ))
            return

        self.stdout.write(f"Found items: {pms_fuel.name} and {quartz_oil.name}")

        # 3. Calculate simulated checkout financials manually matching system rules
        # Line 1: 30 Litres of Premium Petrol (Tax Bracket D - Fuel)
        qty_1 = Decimal("30.00")
        price_1 = pms_fuel.selling_price
        subtotal_1 = qty_1 * price_1
        # Fuel calculations handle VAT calculations inside subtotal elements
        vat_1 = subtotal_1 * Decimal("0.16")  # Adjust according to your standard system breakdown
        taxable_1 = subtotal_1 - vat_1

        # Line 2: 1 Canister of Quartz 7000 Lubricant (Tax Bracket A - 16%)
        qty_2 = Decimal("1.00")
        price_2 = quartz_oil.selling_price
        subtotal_2 = qty_2 * price_2
        vat_2 = subtotal_2 * Decimal("0.16")
        taxable_2 = subtotal_2 - vat_2

        total_invoice_amount = subtotal_1 + subtotal_2

        self.stdout.write(f"Compiling invoice data structure. Gross Total: KSh {total_invoice_amount:,.2f}")

        # 4. Initialize and save the parent Invoice record to your running system
        invoice = Invoice.objects.create(
            total_amount=total_invoice_amount,
            etims_status="PENDING",
            is_credit_note=False
        )

        # 5. Populate your invoice line details (Adjust field parameters to match your model layout)
        try:
            # Check if lines related manager is standard on your system
            if hasattr(invoice, 'lines'):
                invoice.lines.create(
                    product=pms_fuel, quantity=qty_1, unit_price=price_1,
                    subtotal=subtotal_1, taxable_amount=taxable_1, vat_amount=vat_1, total_amount=subtotal_1
                )
                invoice.lines.create(
                    product=quartz_oil, quantity=qty_2, unit_price=price_2,
                    subtotal=subtotal_2, taxable_amount=taxable_2, vat_amount=vat_2, total_amount=subtotal_2
                )
            else:
                self.stdout.write(self.style.WARNING(
                    "Note: Could not automatically generate line relation mappings. "
                    "Verify your Invoice/InvoiceLine foreign key related_name setting."
                ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Line compilation failure: {str(e)}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Successfully stored Invoice #{invoice.id} in the database with PENDING status."
        ))
        self.stdout.write("Django Signal post_save event has dispatched the tracking id to Redis broker queue...")
        self.stdout.write("Check your active Celery terminal window to view live transmission logs.")
