from decimal import Decimal

from django.db import transaction

from .models import Product, StockMovement, Tank


class StockError(Exception):
    pass


@transaction.atomic
def move_stock(*, product, quantity, reason, business_date, reference="", tank=None, user=None, note=""):
    """Record a signed stock movement and update the tank or product balance.

    Fuel goes through a tank. Everything else uses Product.stock_qty.
    """
    quantity = Decimal(quantity)
    if product.is_fuel:
        if tank is None:
            raise StockError(f"{product.name} is fuel, so a tank is required.")
        locked = Tank.objects.select_for_update().get(pk=tank.pk)
        locked.current_level += quantity
        locked.save(update_fields=["current_level", "updated_at"])
    else:
        locked = Product.objects.select_for_update().get(pk=product.pk)
        locked.stock_qty += quantity
        locked.save(update_fields=["stock_qty", "updated_at"])
    return StockMovement.objects.create(
        product=product,
        tank=tank,
        quantity=quantity,
        reason=reason,
        reference=reference,
        business_date=business_date,
        note=note,
        created_by=user,
    )
