import base64, io, logging

logger = logging.getLogger(__name__)

def _generate_qr_data_uri(data: str) -> str | None:
    """
    Generate a PNG QR code for `data` and return a data URI (base64).
    If qrcode/Pillow is not installed or generation fails, return None.
    """
    try:
        import qrcode  # requires `qrcode[pil]` or `qrcode` + Pillow installed

        buf = io.BytesIO()
        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(buf, format="PNG")
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as exc:
        logger.debug("QR generation failed: %s", exc)
        return None