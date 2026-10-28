import httpx
from django.conf import settings
from datetime import datetime

class EtimsOscuClient:
    def __init__(self):
        self.base_url = settings.KRA_ETIMS_BASE_URL  # e.g., https://kra.go.ke
        self.cmc_key = settings.KRA_CMC_KEY          # Your approved Communication Key
        self.tin = settings.KRA_TAXPAYER_PIN          # Seller's KRA PIN
        self.dvc_serial = settings.KRA_DEVICE_SERIAL  # Your approved Device Serial Number

    def generate_invoice_payload(self, invoice):
        """
        Formats your Django Invoice and InvoiceLine database records 
        into the strict eTIMS OSCU structure.
        """
        item_lines = []
        for index, item in enumerate(invoice.lines.all(), start=1):
            item_lines.append({
                "itemSeq": index,                  # Must start at 1
                "itemCd": item.product.sku,        # Item code unique to your inventory
                "itemClsCd": item.product.kra_class_code, # KRA Item Classification (e.g., 50121511)
                "itemNm": item.product.name,
                "pkgUnitCd": "OU",                 # Packaging unit code (OU = Operational Unit / Box / Pieces)
                "qty": float(item.quantity),
                "prc": float(item.unit_price),
                "splyAmt": float(item.subtotal),   # Supply amount (QTY * Price)
                "totDscAmt": float(item.discount or 0.0),
                "taxTyCd": item.product.vat_category, # "A", "B", "C", "D", or "E"
                "taxblAmt": float(item.taxable_amount),
                "taxAmt": float(item.vat_amount),
                "totAmt": float(item.total_amount) # Gross amount for this specific line
            })

        payload = {
            "tin": self.tin,
            "bhfId": settings.KRA_BRANCH_CODE,     # Head office is usually "00"
            "dvcSrlNo": self.dvc_serial,
            "invcNo": invoice.id,                  # Unique progressive invoice integer
            "orgnInvcNo": 0,                       # Greater than 0 only if this is a Credit Note/Refund
            "custTin": invoice.customer.pin or "",  # Mandatory for B2B, empty string for retail B2C
            "custNm": invoice.customer.name or "Retail Customer",
            "salesSttsCd": "02",                   # 02 = Approved/Normal Sale (01 = Copy, 03 = Credit Note)
            "prmtTpVat": "1",                      # Promotion type matching VAT
            "rcptTyCd": "1",                       # 1 = Sale (2 = Credit Note)
            "pmtTyCd": invoice.payment_method_code, # "01" (Cash), "02" (Card), "03" (Mobile Money/M-Pesa)
            "salesDt": datetime.now().strftime("%Y%m%d"),
            "salesTm": datetime.now().strftime("%H%M%S"),
            "totItemCnt": invoice.lines.count(),
            "taxblAmtA": float(invoice.taxable_amount_a or 0.0), # Grouped totals matching tax criteria A
            "taxblAmtB": float(invoice.taxable_amount_b or 0.0),
            "taxblAmtC": float(invoice.taxable_amount_c or 0.0),
            "taxblAmtD": float(invoice.taxable_amount_d or 0.0),
            "taxAmtA": float(invoice.vat_amount_a or 0.0),
            "taxAmtB": float(invoice.vat_amount_b or 0.0),
            "taxAmtC": float(invoice.vat_amount_c or 0.0),
            "taxAmtD": float(invoice.vat_amount_d or 0.0),
            "totTaxblAmt": float(invoice.total_taxable_amount),
            "totTaxAmt": float(invoice.total_vat_amount),
            "totAmt": float(invoice.total_invoice_amount),
            "itemList": item_lines
        }
        return payload

    def transmit(self, payload):
        """Dispatches data using the mandatory OSCU cmcKey validation header."""
        endpoint = f"{self.base_url}/api/v1/oscu/sales/saveInvoice"
        
        headers = {
            "cmcKey": self.cmc_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            return response.json()
