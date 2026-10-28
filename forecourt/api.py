"""Gateway endpoints for the IFSF forecourt controller.

The controller (or a small bridge service next to it) POSTs each completed
dispense to /api/ifsf/transaction/ with the shared token in X-IFSF-Token.
Each pump is identified by its ifsf_node_id and each nozzle by its number.
"""
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import FuellingTransaction, Nozzle, Pump


def _authorised(request) -> bool:
    return request.headers.get("X-IFSF-Token") == settings.IFSF_API_TOKEN


def _dec(payload, key, required=False):
    value = payload.get(key)
    if value in (None, ""):
        if required:
            raise ValueError(f"'{key}' is required")
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"'{key}' must be a number")


@require_http_methods(["GET"])
def nodes(request):
    if not _authorised(request):
        return JsonResponse({"error": "invalid token"}, status=401)
    data = [
        {
            "ifsf_node_id": pump.ifsf_node_id,
            "pump": pump.number,
            "nozzles": [
                {"number": n.number, "tank": n.tank.name, "product": n.tank.product.code}
                for n in pump.nozzles.filter(is_active=True).select_related("tank__product")
            ],
        }
        for pump in Pump.objects.filter(is_active=True)
    ]
    return JsonResponse({"nodes": data})


@csrf_exempt
@require_http_methods(["POST"])
def transaction_in(request):
    if not _authorised(request):
        return JsonResponse({"error": "invalid token"}, status=401)
    try:
        payload = json.loads(request.body or b"{}")
        node_id = str(payload.get("node_id", "")).strip()
        nozzle_no = int(payload.get("nozzle"))
        volume = _dec(payload, "volume", required=True)
        amount = _dec(payload, "amount", required=True)
        total_vol = _dec(payload, "totalizer_volume")
        total_amt = _dec(payload, "totalizer_amount")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return JsonResponse({"error": str(exc) or "invalid payload"}, status=400)

    try:
        nozzle = Nozzle.objects.select_related("pump", "tank__product").get(
            pump__ifsf_node_id=node_id, number=nozzle_no, is_active=True, pump__is_active=True
        )
    except Nozzle.DoesNotExist:
        return JsonResponse({"error": f"unknown node/nozzle {node_id}/{nozzle_no}"}, status=404)

    occurred = parse_datetime(str(payload.get("timestamp", ""))) or timezone.now()
    if timezone.is_naive(occurred):
        occurred = timezone.make_aware(occurred)

    from shifts.models import Shift

    shift = Shift.objects.filter(status=Shift.Status.OPEN).first()
    external_id = str(payload.get("transaction_id", ""))[:80]
    try:
        with transaction.atomic():
            tx = FuellingTransaction.objects.create(
                nozzle=nozzle,
                external_id=external_id,
                volume=volume,
                amount=amount,
                unit_price=(amount / volume).quantize(Decimal("0.01")) if volume else nozzle.tank.product.selling_price,
                totalizer_volume=total_vol,
                totalizer_amount=total_amt,
                occurred_at=occurred,
                shift=shift,
                raw=payload,
            )
            if total_vol is not None:
                nozzle.totalizer_volume = total_vol
            if total_amt is not None:
                nozzle.totalizer_amount = total_amt
            nozzle.save(update_fields=["totalizer_volume", "totalizer_amount", "updated_at"])
    except IntegrityError:
        return JsonResponse({"status": "duplicate", "transaction_id": external_id}, status=200)
    return JsonResponse({"status": "created", "id": tx.pk}, status=201)
