import logging
from celery import shared_task
from django.conf import settings
from decimal import Decimal
import datetime
import httpx

logger = logging.getLogger(__name__)

@shared_task(
    bind=True, 
    max_retries=5, 
    default_retry_delay=60,  # Wait 60 seconds before the first retry
    retry_backoff=True,      # Multiply delay exponentially on subsequent failures
    retry_backoff_max=600     # Never wait more than 10 minutes between retries
)
def transmit_invoice_to_etims_task(self, invoice_id):
    """
    Background worker that packages live Django Invoice lines into the strict 
    KRA OSCU payload layout and handles responses asynchronously.
    """
    from .models import Invoice  # Lazy import to prevent circular loading loops

    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        logger.error(f"eTIMS Sync Failed: Invoice #{invoice_id} not found in database.")
        return

    # Skip processing if already processed successfully
    if invoice.etims_status == "TRANSMITTED":
        return

    # 1. Dynamically structure item lines array matching KRA requirements
    item_lines = []
    total_taxable_amt = Decimal("0.00")
    total_tax_amt = Decimal("0.00")

    # This loops through your invoice lines layout (adjust related_name if different)
    for index, item in enumerate(invoice.lines.all(), start=1):
        item_lines.append({
            "itemSeq": index,
            "itemCd": item.product.sku,
            "itemClsCd": item.product.kra_class_code,
            "itemNm": item.product.name,
            "pkgUnitCd": "OU",
            "qty": float(item.quantity),
            "prc": float(item.unit_price),
            "splyAmt": float(item.subtotal),
            "totDscAmt": float(getattr(item, 'discount', 0) or 0.0),
            "taxTyCd": item.product.vat_category, # e.g. "A" for 16% standard VAT
            "taxblAmt": float(item.taxable_amount),
            "taxAmt": float(item.vat_amount),
            "totAmt": float(item.total_amount)
        })
        total_taxable_amt += Decimal(str(item.taxable_amount))
        total_tax_amt += Decimal(str(item.vat_amount))

    # 2. Build the top-level OSCU envelope
    now = datetime.datetime.now()
    payload = {
        "tin": settings.KRA_TAXPAYER_PIN,
        "bhfId": settings.KRA_BRANCH_CODE,
        "dvcSrlNo": settings.KRA_DEVICE_SERIAL,
        "invcNo": invoice.id,
        "orgnInvcNo": 0,
        "custTin": getattr(invoice.customer, 'pin', '') or '',
        "custNm": getattr(invoice.customer, 'name', 'Retail Customer') or 'Retail Customer',
        "salesSttsCd": "02",  # 02 = Approved Normal Sale
        "prmtTpVat": "1",
        "rcptTyCd": "1",
        "pmtTyCd": getattr(invoice, 'payment_method_code', '03'), # Default to 03 for Mobile Money
        "salesDt": now.strftime("%Y%m%d"),
        "salesTm": now.strftime("%H%M%S"),
        "totItemCnt": len(item_lines),
        "taxblAmtA": float(total_taxable_amt), # Assuming Tax Category A (adjust loops for multi-tax mixes)
        "taxblAmtB": 0.0,
        "taxblAmtC": 0.0,
        "taxblAmtD": 0.0,
        "taxAmtA": float(total_tax_amt),
        "taxAmtB": 0.0,
        "taxAmtC": 0.0,
        "taxAmtD": 0.0,
        "totTaxblAmt": float(total_taxable_amt),
        "totTaxAmt": float(total_tax_amt),
        "totAmt": float(invoice.total_amount),
        "itemList": item_lines
    }

    # 3. Transmit using your configured settings credentials via HTTPX
    endpoint = f"{settings.KRA_ETIMS_BASE_URL}/api/v1/oscu/sales/saveInvoice"
    headers = {
        "cmcKey": settings.KRA_CMC_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        with httpx.Client(timeout=25.0) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status() # Trigger exception for 5xx/4xx codes
            result = response.json()

        # KRA eTIMS Response mapping validation
        if result.get("resultCd") == "000": # 000 is the official success status code
            invoice.etims_receipt_number = result.get("rcptNo")
            invoice.etims_signature = result.get("rcptSign")
            invoice.etims_internal_data = result.get("intrlData")
            invoice.etims_status = "TRANSMITTED"
            invoice.etims_error_log = ""
            invoice.save(update_fields=['etims_receipt_number', 'etims_signature', 'etims_internal_data', 'etims_status', 'etims_error_log'])
            logger.info(f"eTIMS successfully synchronized for Invoice #{invoice.id}")
        else:
            # Payload validation failure on KRA side (e.g. invalid item classification format)
            invoice.etims_status = "FAILED"
            invoice.etims_error_log = f"KRA Error [{result.get('resultCd')}]: {result.get('resultMsg')}"
            invoice.save(update_fields=['etims_status', 'etims_error_log'])
            logger.error(f"eTIMS Processing Rejected for Invoice #{invoice.id}: {invoice.etims_error_log}")

    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        # Catch connection failures, server 503s, and timeouts to retry later safely
        invoice.etims_error_log = f"Network Transport Error: {str(exc)}"
        invoice.save(update_fields=['etims_error_log'])
        logger.warning(f"eTIMS link timeout on Invoice #{invoice.id}. Retrying task... Error: {exc}")
        raise self.retry(exc=exc)
