import datetime
import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.db.models import Sum
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from forecourt.models import Product, Station, Tank
from ledger.models import JournalLine
from ledger.services import LedgerError, post_journal
from purchases.models import Purchase, PurchaseLine, Supplier
from purchases.services import PurchaseError, post_purchase
from reports.models import ReportRun
from reports.pdf import render_pdf
from reports.tasks import build_report
from sales.models import Customer, Invoice
from sales.services import SaleError, record_customer_payment, record_sale
from shifts.models import Shift
from shifts.services import ShiftError, close_shift, open_shift, save_backup, verify_shift


class BaseCase(TestCase):
    def setUp(self):
        call_command("seed_bonje", verbosity=0)
        self.user = User.objects.create_user("boss", password="pw12345!", role="manager")
        self.station = Station.objects.get()
        Tank.objects.update(current_level=Decimal("20000"))
        self.pms = Product.objects.get(code="PMS")

    def fill_meters(self, shift, extra_litres=Decimal("0"), product=None):
        """Close every nozzle at its opening value, except one petrol nozzle that sold extra_litres."""
        target = shift.readings.filter(nozzle__tank__product=product or self.pms).first()
        for r in shift.readings.all():
            sold = extra_litres if r.pk == target.pk else Decimal("0")
            r.closing_litres = r.opening_litres + sold
            r.closing_cash_meter = r.opening_cash_meter + sold * r.unit_price
            r.save()


class LedgerTests(BaseCase):
    def test_unbalanced_journal_rejected(self):
        with self.assertRaises(LedgerError):
            post_journal(date=timezone.localdate(), memo="bad", lines=[("1000", 100, 0), ("4000", 0, 90)])


@override_settings(STATION_BACKUP_DIR=Path(tempfile.mkdtemp()))
class ShiftCycleTests(BaseCase):
    def test_full_cycle(self):
        shift = open_shift(self.station, self.user)
        self.assertEqual(shift.readings.count(), 8)
        with self.assertRaises(ShiftError):
            open_shift(self.station, self.user)

        record_sale(shift=shift, product=self.pms, quantity=100, payment_method="CASH", user=self.user)
        self.fill_meters(shift, Decimal("100"))

        today = timezone.localdate()
        with self.assertRaises(ShiftError):
            close_shift(shift, self.user)  # not verified yet
        verify_shift(shift, self.user, today)
        with self.assertRaises(ShiftError):
            close_shift(shift, self.user)  # not backed up yet
        path, _ = save_backup(shift)
        self.assertTrue(path.exists())
        close_shift(shift, self.user)

        shift.refresh_from_db()
        self.assertEqual(shift.status, Shift.Status.CLOSED)
        self.assertEqual(Tank.objects.get(name="T1").current_level, Decimal("19900"))
        debit = JournalLine.objects.aggregate(t=Sum("debit"))["t"]
        credit = JournalLine.objects.aggregate(t=Sum("credit"))["t"]
        self.assertEqual(debit, credit)

        # Next shift opens where this one closed.
        second = open_shift(self.station, self.user)
        reading = second.readings.filter(nozzle__tank__product=self.pms).first()
        first = shift.readings.get(nozzle=reading.nozzle)
        self.assertEqual(reading.opening_litres, first.closing_litres)

    def test_shortage_needs_acknowledgement(self):
        shift = open_shift(self.station, self.user)
        self.fill_meters(shift, Decimal("50"))  # 50 L dispensed, nothing recorded
        with self.assertRaises(ShiftError):
            verify_shift(shift, self.user, timezone.localdate())
        verify_shift(shift, self.user, timezone.localdate(), accept_variance=True)
        self.assertTrue(Shift.objects.get(pk=shift.pk).variance_accepted)

    def test_cannot_verify_future_date(self):
        shift = open_shift(self.station, self.user)
        self.fill_meters(shift)
        with self.assertRaises(ShiftError):
            verify_shift(shift, self.user, timezone.localdate() + datetime.timedelta(days=2))

    def test_sale_needs_open_shift(self):
        shift = open_shift(self.station, self.user)
        self.fill_meters(shift)
        verify_shift(shift, self.user, timezone.localdate())
        with self.assertRaises(SaleError):
            record_sale(shift=shift, product=self.pms, quantity=1, payment_method="CASH", user=self.user)

    def test_reports_and_page_range_pdf(self):
        shift = open_shift(self.station, self.user)
        record_sale(shift=shift, product=self.pms, quantity=40, payment_method="CASH", user=self.user)
        self.fill_meters(shift, Decimal("40"))
        verify_shift(shift, self.user, timezone.localdate())
        save_backup(shift)
        close_shift(shift, self.user)

        run = ReportRun.objects.create(kind="DSSR", report_date=timezone.localdate(), requested_by=self.user)
        build_report(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.status, ReportRun.Status.DONE, run.error)
        self.assertEqual(len(run.pages), 4)
        self.assertTrue(render_pdf(run, 1, 1).startswith(b"%PDF"))
        self.assertTrue(render_pdf(run, 2, 4, copies=2).startswith(b"%PDF"))
        with self.assertRaises(ValueError):
            render_pdf(run, 5, 6)

        for kind in ("TRIAL", "DEBTORS"):
            other = ReportRun.objects.create(kind=kind, report_date=timezone.localdate())
            build_report(other.pk)
            other.refresh_from_db()
            self.assertEqual(other.status, ReportRun.Status.DONE, other.error)


class CreditTests(BaseCase):
    def test_credit_limit_invoice_and_payment(self):
        shift = open_shift(self.station, self.user)
        customer = Customer.objects.create(name="Acme Haulage", credit_limit=Decimal("5000"))
        with self.assertRaises(SaleError):
            record_sale(shift=shift, product=self.pms, quantity=100, payment_method="CREDIT", user=self.user, customer=customer)
        sale = record_sale(shift=shift, product=self.pms, quantity=10, payment_method="CREDIT", user=self.user, customer=customer)
        self.assertEqual(sale.amount, Decimal("1900.00"))
        self.assertEqual(customer.balance, Decimal("1900.00"))
        record_customer_payment(customer=customer, amount=Decimal("1900"), method="CASH", date=timezone.localdate(), user=self.user)
        self.assertEqual(customer.balance, Decimal("0.00"))
        self.assertEqual(Invoice.objects.get().status, "PAID")


class PurchaseTests(BaseCase):
    def test_post_purchase_updates_tank_and_blocks_overfill(self):
        supplier = Supplier.objects.create(name="Fuel Co")
        tank = Tank.objects.get(name="T1")
        purchase = Purchase.objects.create(supplier=supplier, invoice_no="A1", delivery_date=timezone.localdate())
        PurchaseLine.objects.create(purchase=purchase, product=self.pms, tank=tank, quantity=5000, unit_cost=Decimal("171"))
        post_purchase(purchase, self.user)
        tank.refresh_from_db()
        self.assertEqual(tank.current_level, Decimal("25000"))
        self.assertEqual(supplier.balance, Decimal("855000.00"))

        big = Purchase.objects.create(supplier=supplier, invoice_no="A2", delivery_date=timezone.localdate())
        PurchaseLine.objects.create(purchase=big, product=self.pms, tank=tank, quantity=9000, unit_cost=Decimal("171"))
        with self.assertRaises(PurchaseError):
            post_purchase(big, self.user)


@override_settings(IFSF_API_TOKEN="secret-token")
class IfsfApiTests(BaseCase):
    def post(self, payload, token="secret-token"):
        return self.client.post(
            reverse("forecourt:ifsf_transaction"), data=json.dumps(payload),
            content_type="application/json", HTTP_X_IFSF_TOKEN=token,
        )

    def test_transaction_flow(self):
        payload = {"node_id": "IFSF-BONJE-01", "nozzle": 1, "volume": "20.5", "amount": "3895.00",
                   "totalizer_volume": "1020.50", "transaction_id": "T-1"}
        self.assertEqual(self.post(payload, token="wrong").status_code, 401)
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(self.post(payload).json()["status"], "duplicate")
        self.assertEqual(self.post({**payload, "node_id": "NOPE"}).status_code, 404)
        self.assertEqual(self.post({"node_id": "IFSF-BONJE-01", "nozzle": 1}).status_code, 400)
        from forecourt.models import Nozzle
        nozzle = Nozzle.objects.get(pump__ifsf_node_id="IFSF-BONJE-01", number=1)
        self.assertEqual(nozzle.totalizer_volume, Decimal("1020.50"))

    def test_nodes_listing(self):
        response = self.client.get(reverse("forecourt:ifsf_nodes"), HTTP_X_IFSF_TOKEN="secret-token")
        self.assertEqual(len(response.json()["nodes"]), 4)


class PageSmokeTests(BaseCase):
    """Every screen renders for a manager, which catches template and URL mistakes."""

    def test_pages_render(self):
        client = Client()
        client.force_login(self.user)
        names = [
            "forecourt:dashboard", "forecourt:products", "forecourt:product_add", "forecourt:tanks", "forecourt:tank_add",
            "forecourt:pumps", "forecourt:pump_add", "forecourt:nozzles", "forecourt:nozzle_add", "shifts:list",
            "sales:list", "sales:entry", "sales:customers", "sales:customer_add", "sales:invoices", "sales:payment_add",
            "purchases:list", "purchases:add", "purchases:suppliers", "purchases:supplier_add", "purchases:payment_add",
            "ledger:accounts", "ledger:journal", "ledger:expenses", "ledger:expense_add", "reports:home",
        ]
        for name in names:
            response = client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_shift_screens_and_sale_entry(self):
        client = Client()
        client.force_login(self.user)
        client.post(reverse("shifts:open"))
        shift = Shift.objects.get()
        for name, args in [("shifts:detail", [shift.pk]), ("shifts:readings", [shift.pk]), ("shifts:verify", [shift.pk]),
                           ("shifts:dips", [shift.pk, "close"])]:
            self.assertEqual(client.get(reverse(name, args=args)).status_code, 200, name)
        response = client.post(reverse("sales:entry"), {
            "product": self.pms.pk, "quantity": "10", "payment_method": "CASH", "unit_price": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=", response["Location"])
        self.assertEqual(client.get(response["Location"]).status_code, 200)

    def test_attendant_cannot_reach_setup(self):
        attendant = User.objects.create_user("att", password="pw12345!", role="attendant")
        client = Client()
        client.force_login(attendant)
        self.assertEqual(client.get(reverse("forecourt:products")).status_code, 403)
        self.assertEqual(client.get(reverse("forecourt:dashboard")).status_code, 200)

    def test_login_required(self):
        response = Client().get(reverse("forecourt:dashboard"))
        self.assertEqual(response.status_code, 302)
