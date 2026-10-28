from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from common.utils import money
from forecourt.models import Tank
from forecourt.stock import move_stock
from ledger import chart
from ledger.services import post_journal

from .models import Purchase, SupplierPayment

RECEIPT_ACCOUNT = {"CASH": chart.CASH, "BANK": chart.BANK, "MPESA": chart.MPESA}


class PurchaseError(Exception):
    pass


@transaction.atomic
def post_purchase(purchase: Purchase, user=None):
    """Receive stock into tanks/shelves, update cost prices and book the payable."""
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status == Purchase.Status.POSTED:
        raise PurchaseError("This purchase is already posted.")
    lines = list(purchase.lines.select_related("product", "tank"))
    if not lines:
        raise PurchaseError("Add at least one line before posting.")

    fuel_total = Decimal("0")
    shop_total = Decimal("0")
    for line in lines:
        product = line.product
        if product.is_fuel:
            if line.tank is None:
                raise PurchaseError(f"Choose a tank for {product.name}.")
            if line.tank.product_id != product.pk:
                raise PurchaseError(f"{line.tank.name} does not hold {product.name}.")
            tank = Tank.objects.get(pk=line.tank_id)
            if tank.current_level + line.quantity > tank.capacity:
                room = tank.capacity - tank.current_level
                raise PurchaseError(f"{tank.name} can only take {room:,.0f} more litres; this delivery is {line.quantity:,.0f}.")
            fuel_total += line.line_total
        else:
            shop_total += line.line_total
        move_stock(
            product=product, quantity=line.quantity, reason="PURCHASE", business_date=purchase.delivery_date,
            reference=purchase.invoice_no, tank=line.tank if product.is_fuel else None, user=user,
        )
        product.cost_price = line.unit_cost
        product.save(update_fields=["cost_price", "updated_at"])

    post_journal(
        date=purchase.delivery_date,
        memo=f"Purchase {purchase.invoice_no} from {purchase.supplier.name}",
        lines=[
            (chart.INVENTORY_FUEL, fuel_total, 0),
            (chart.INVENTORY_SHOP, shop_total, 0),
            (chart.PAYABLES, 0, fuel_total + shop_total),
        ],
        source=f"purchases.Purchase:{purchase.pk}",
        user=user,
    )
    purchase.status = Purchase.Status.POSTED
    purchase.posted_at = timezone.now()
    purchase.save(update_fields=["status", "posted_at", "updated_at"])
    return purchase


@transaction.atomic
def pay_supplier(*, supplier, amount, method, date, reference="", user=None):
    amount = money(amount)
    if amount <= 0:
        raise PurchaseError("Payment must be greater than zero.")
    payment = SupplierPayment.objects.create(
        supplier=supplier, date=date, amount=amount, method=method, reference=reference, created_by=user
    )
    post_journal(
        date=date,
        memo=f"Payment to {supplier.name}",
        lines=[(chart.PAYABLES, amount, 0), (RECEIPT_ACCOUNT[method], 0, amount)],
        source=f"purchases.SupplierPayment:{payment.pk}",
        user=user,
    )
    return payment
