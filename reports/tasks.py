import logging
import datetime
from decimal import Decimal
import httpx
from bs4 import BeautifulSoup
from celery import shared_task
from django.conf import settings

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
    KRA OSCU payload layout, handling complex TotalEnergies multi-tax configurations.
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

    # 1. Initialize item variables and separate tax accumulators
    item_lines = []
    
    taxable_amt_A = Decimal("0.00")  # 16% Lubricants/Shop items
    tax_amt_A = Decimal("0.00")
    
    taxable_amt_B = Decimal("0.00")  # 0% Zero-Rated LPG Cooking Gas
    tax_amt_B = Decimal("0.00")
    
    taxable_amt_C = Decimal("0.00")  # Exempt Solar hardware
    tax_amt_C = Decimal("0.00")
    
    taxable_amt_D = Decimal("0.00")  # Fuel bracket (Petrol/Diesel/Kerosene)
    tax_amt_D = Decimal("0.00")

    # Dynamic line parsing matching product categories
    for index, item in enumerate(invoice.lines.all(), start=1):
        # Resolve KRA attributes safely using your system's fields
        kra_meta = resolve_kra_product_metadata(item.product)
        category = kra_meta["tax_category"]
        class_code = kra_meta["class_code"]

        subtotal = Decimal(str(item.subtotal))
        taxable_amount = Decimal(str(item.taxable_amount))
        vat_amount = Decimal(str(item.vat_amount))
        total_amount = Decimal(str(item.total_amount))

        item_lines.append({
            "itemSeq": index,
            "itemCd": item.product.code,  # 🌟 Changed from .sku to .code
            "itemClsCd": class_code,
            "itemNm": item.product.name,
            "pkgUnitCd": "OU",
            "qty": float(item.quantity),
            "prc": float(item.unit_price),
            "splyAmt": float(subtotal),
            "totDscAmt": float(getattr(item, 'discount', 0) or 0.0),
            "taxTyCd": category,
            "taxblAmt": float(taxable_amount),
            "taxAmt": float(vat_amount),
            "totAmt": float(total_amount)
        })


        # Accumulate sums inside their respective statutory target codes
        if category == "A":
            taxable_amt_A += taxable_amount
            tax_amt_A += vat_amount
        elif category == "B":
            taxable_amt_B += taxable_amount
            tax_amt_B += vat_amount
        elif category == "C":
            taxable_amt_C += taxable_amount
            tax_amt_C += vat_amount
        elif category == "D":
            taxable_amt_D += taxable_amount
            tax_amt_D += vat_amount

    # 2. Build the top-level compliant OSCU envelope
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
        "pmtTyCd": getattr(invoice, 'payment_method_code', '03'), # Default to 03 for Mobile Money (M-Pesa)
        "salesDt": now.strftime("%Y%m%d"),
        "salesTm": now.strftime("%H%M%S"),
        "totItemCnt": len(item_lines),
        "taxblAmtA": float(taxable_amt_A),
        "taxblAmtB": float(taxable_amt_B),
        "taxblAmtC": float(taxable_amt_C),
        "taxblAmtD": float(taxable_amt_D),
        "taxAmtA": float(tax_amt_A),
        "taxAmtB": float(tax_amt_B),
        "taxAmtC": float(tax_amt_C),
        "taxAmtD": float(tax_amt_D),
        "totTaxblAmt": float(taxable_amt_A + taxable_amt_B + taxable_amt_C + taxable_amt_D),
        "totTaxAmt": float(tax_amt_A + tax_amt_B + tax_amt_C + tax_amt_D),
        "totAmt": float(invoice.total_amount),
        "itemList": item_lines
    }

    # 3. Transmit to KRA OSCU backend URL
    endpoint = f"{settings.KRA_ETIMS_BASE_URL}/api/v1/oscu/sales/saveInvoice"
    headers = {
        "cmcKey": settings.KRA_CMC_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        with httpx.Client(timeout=25.0) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status() 
            result = response.json()

        if result.get("resultCd") == "000":
            invoice.etims_receipt_number = result.get("rcptNo")
            invoice.etims_signature = result.get("rcptSign")
            invoice.etims_internal_data = result.get("intrlData")
            invoice.etims_status = "TRANSMITTED"
            invoice.etims_error_log = ""
            invoice.save(update_fields=['etims_receipt_number', 'etims_signature', 'etims_internal_data', 'etims_status', 'etims_error_log'])
            logger.info(f"eTIMS successfully synchronized for Invoice #{invoice.id}")
        else:
            invoice.etims_status = "FAILED"
            invoice.etims_error_log = f"KRA Error [{result.get('resultCd')}]: {result.get('resultMsg')}"
            invoice.save(update_fields=['etims_status', 'etims_error_log'])
            logger.error(f"eTIMS Processing Rejected for Invoice #{invoice.id}: {invoice.etims_error_log}")

    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        invoice.etims_error_log = f"Network Transport Error: {str(exc)}"
        invoice.save(update_fields=['etims_error_log'])
        logger.warning(f"eTIMS link timeout on Invoice #{invoice.id}. Retrying task... Error: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_epra_fuel_prices_task(self):
    """
    Scrapes the official EPRA portal to automatically update 
    TotalEnergies forecourt pump prices on the 14th of every month.
    """
    from .models import Product
    
    url = "https://epra.go.ke"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    target_town = getattr(settings, 'EPRA_OPERATING_TOWN', 'Nairobi')
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'html.parser')
        prices = {"PMS": None, "AGO": None, "IK": None}
        
        for row in soup.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            # Locate target depot pricing criteria line matching location configurations
            if len(cells) >= 4 and any(target_town.lower() in str(cell).lower() for cell in cells):
                # Clean up formatting strings to prevent floating math processing bugs
                prices["PMS"] = Decimal(cells[1].replace(",", ""))
                prices["AGO"] = Decimal(cells[2].replace(",", ""))
                prices["IK"] = Decimal(cells[3].replace(",", ""))
                break

        sku_mappings = {
            "TOT-EXC-PMS": {"key": "PMS", "cls": "15101506", "name": "Total Excellium Petrol (PMS)"},
            "TOT-EXC-AGO": {"key": "AGO", "cls": "15101505", "name": "Total Excellium Diesel (AGO)"},
            "TOT-EXC-IK":  {"key": "IK",  "cls": "15101512", "name": "Total Kerosene (IK)"}
        }
        
        updated_count = 0
        for sku, meta in sku_mappings.items():
            new_price = prices.get(meta["key"])
            if new_price:
                product, created = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        'name': meta["name"],
                        'kra_class_code': meta["cls"],
                        'vat_category': "D",
                        'unit_price': new_price
                    }
                )
                if not created and product.unit_price != new_price:
                    product.unit_price = new_price
                    product.save(update_fields=['unit_price'])
                    updated_count += 1
                    logger.info(f"EPRA Auto-Sync: Updated {sku} to KSh {new_price} for {target_town}")

        return f"EPRA Price check complete. Updated {updated_count} forecourt items."

    except Exception as exc:
        logger.error(f"EPRA monthly price scrape routine failed: {str(exc)}")
        raise self.retry(exc=exc)

# --- Explicit Tax & Classification Mapping Registry ---
KRA_CLASSIFICATION_MAP = {
    "TOT-EXC-PMS": {"class_code": "15101506", "tax_category": "D"},  # Petrol
    "TOT-EXC-AGO": {"class_code": "15101505", "tax_category": "D"},  # Diesel
    "TOT-EXC-IK":  {"class_code": "15101512", "tax_category": "D"},  # Kerosene
    "TOT-GAS-3KG-REFILL":  {"class_code": "15111510", "tax_category": "B"}, # LPG 0%
    "TOT-GAS-6KG-REFILL":  {"class_code": "15111510", "tax_category": "B"},
    "TOT-GAS-13KG-REFILL": {"class_code": "15111510", "tax_category": "B"},
    "TOT-GAS-22.5KG-REFILL": {"class_code": "15111510", "tax_category": "B"},
    "TOT-GAS-50KG-REFILL": {"class_code": "15111510", "tax_category": "B"},
}

# --- Runtime Fallback evaluation helper function ---
def resolve_kra_product_metadata(product):
    """
    Resolves class code and tax bracket specifications using the product code 
    or its structural 'kind' definition dynamically.
    """
    # Try an exact code lookup first
    if product.code in KRA_CLASSIFICATION_MAP:
        return KRA_CLASSIFICATION_MAP[product.code]
        
    # Fallback to general category mappings based on the 'kind' column
    kind_lower = (product.kind or "").lower()
    if "fuel" in kind_lower:
        return {"class_code": "15101506", "tax_category": "D"}
    elif "lpg" in kind_lower or "gas" in kind_lower:
        return {"class_code": "15111510", "tax_category": "B"}
    else:
        # Default to standard 16% VAT for Lubricants and Shop Stock
        return {"class_code": "15121501", "tax_category": "A"}
# --- Explicit Tax & Classification Mapping Registry ---
KRA_CLASSIFICATION_MAP = {
    "TOT-EXC-PMS": {"class_code": "15101506", "tax_category": "D"},  # Petrol
    "TOT-EXC-AGO": {"class_code": "15101505", "tax_category": "D"},  # Diesel
    "TOT-EXC-IK":  {"class_code": "15101512", "tax_category": "D"},  # Kerosene
    "TOT-GAS-3KG-REFILL":  {"class_code": "15111510", "tax_category": "B"}, # LPG 0%
    "TOT-GAS-6KG-REFILL":  {"class_code": "15111510", "tax_category": "B"},
    "TOT-GAS-13KG-REFILL": {"class_code": "15111510", "tax_category": "B"},
    "TOT-GAS-22.5KG-REFILL": {"class_code": "15111510", "tax_category": "B"},
    "TOT-GAS-50KG-REFILL": {"class_code": "15111510", "tax_category": "B"},
}

# --- Runtime Fallback evaluation helper function ---
def resolve_kra_product_metadata(product):
    """
    Resolves class code and tax bracket specifications using the product code 
    or its structural 'kind' definition dynamically.
    """
    # Try an exact code lookup first
    if product.code in KRA_CLASSIFICATION_MAP:
        return KRA_CLASSIFICATION_MAP[product.code]
        
    # Fallback to general category mappings based on the 'kind' column
    kind_lower = (product.kind or "").lower()
    if "fuel" in kind_lower:
        return {"class_code": "15101506", "tax_category": "D"}
    elif "lpg" in kind_lower or "gas" in kind_lower:
        return {"class_code": "15111510", "tax_category": "B"}
    else:
        # Default to standard 16% VAT for Lubricants and Shop Stock
        return {"class_code": "15121501", "tax_category": "A"}

    
