from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from common.utils import money
from forecourt.stock import move_stock
from ledger import chart
from ledger.services import post_journal

from .models import Customer, CustomerPayment, Invoice, Sale

PAYMENT_ACCOUNT = {
    "CASH": chart.CASH,
    "MPESA": chart.MPESA,
    "CARD": chart.CARD,
    "CREDIT": chart.RECEIVABLES,
}
RECEIPT_ACCOUNT = {"CASH": chart.CASH, "BANK": chart.BANK, "MPESA": chart.MPESA}


class SaleError(Exception):
    pass


@transaction.atomic
def record_sale(
    *, shift, product, quantity, payment_method, user, unit_price=None, customer=None, nozzle=None,
    reference="", vehicle_reg="",
):
    """Record one sale line and post it to the ledger.

    Fuel sales are payment allocations: pump meters drive fuel stock at shift
    close. Non-fuel sales reduce stock immediately.
    """
    if not shift.is_open:
        raise SaleError("This shift is not open for sales. Reopen it or start a new shift.")
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise SaleError("Quantity must be greater than zero.")
    price = money(unit_price if unit_price else product.selling_price)
    if price <= 0:
        raise SaleError(f"{product.name} has no selling price. Set one under Products first.")
    amount = money(quantity * price)
    today = timezone.localdate()

    invoice = None
    if payment_method == Sale.Method.CREDIT:
        if customer is None:
            raise SaleError("Choose the credit customer for an invoice sale.")
        if not customer.is_active:
            raise SaleError(f"{customer.name} is not active.")
        if customer.credit_limit and customer.balance + amount > customer.credit_limit:
            raise SaleError(
                f"This would take {customer.name} over their credit limit "
                f"({customer.balance:,.2f} owed, limit {customer.credit_limit:,.2f})."
            )
        invoice = Invoice.objects.create(customer=customer, issue_date=today, total_amount=amount)
    else:
        customer = None

    sale = Sale.objects.create(
        shift=shift, product=product, nozzle=nozzle, quantity=quantity, unit_price=price, amount=amount,
        payment_method=payment_method, customer=customer, invoice=invoice, reference=reference,
        vehicle_reg=vehicle_reg.upper(), created_by=user,
    )

    income = chart.FUEL_SALES if product.is_fuel else chart.SHOP_SALES
    lines = [(PAYMENT_ACCOUNT[payment_method], amount, 0), (income, 0, amount)]
    if not product.is_fuel:
        move_stock(
            product=product, quantity=-quantity, reason="SALE", business_date=today,
            reference=f"SALE{sale.pk}", user=user,
        )
        cost = money(quantity * product.cost_price)
        lines += [(chart.COGS_SHOP, cost, 0), (chart.INVENTORY_SHOP, 0, cost)]
    post_journal(date=today, memo=f"{product.name} sale", lines=lines, source=f"sales.Sale:{sale.pk}", user=user)
    return sale


@transaction.atomic
def record_customer_payment(*, customer, amount, method, date, reference="", user=None):
    amount = money(amount)
    if amount <= 0:
        raise SaleError("Payment must be greater than zero.")
    payment = CustomerPayment.objects.create(
        customer=customer, date=date, amount=amount, method=method, reference=reference, created_by=user
    )
    remaining = amount
    for invoice in customer.invoices.filter(status=Invoice.Status.OPEN).order_by("issue_date", "id").select_for_update():
        if remaining <= 0:
            break
        pay = min(invoice.balance, remaining)
        invoice.amount_paid += pay
        if invoice.balance <= 0:
            invoice.status = Invoice.Status.PAID
        invoice.save(update_fields=["amount_paid", "status", "updated_at"])
        remaining -= pay
    post_journal(
        date=date,
        memo=f"Payment from {customer.name}",
        lines=[(RECEIPT_ACCOUNT[method], amount, 0), (chart.RECEIVABLES, 0, amount)],
        source=f"sales.CustomerPayment:{payment.pk}",
        user=user,
    )
    return payment
