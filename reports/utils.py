import io
import base64
import qrcode

def fmt(value):
    """Fallback generic list layout formatting utility."""
    if value is None:
        return ""
    return str(value)

def generate_etims_qr_code(invoice_number, receipt_number, signature, internal_data):
    """
    Generates a legal KRA eTIMS verification QR code image encoded as Base64.
    """
    verification_url = (
        f"https://etims.kra.go.ke/common/link/etims/receipt/index"
        f"?invNo={invoice_number}"
        f"&rcptNo={receipt_number}"
        f"&rcptSign={signature}"
        f"&intrlData={internal_data}"
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"