import base64
import hmac
import io
from datetime import datetime, timezone

import pyotp
import qrcode
import qrcode.image.svg

from ..settings import settings

VALID_WINDOW = 1


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=settings.totp_issuer)


def qr_svg_data_url(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def verify(secret: str, code: str, last_used_step: int = 0) -> int | None:
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    current = totp.timecode(datetime.now(timezone.utc))
    for step in range(current - VALID_WINDOW, current + VALID_WINDOW + 1):
        if step > last_used_step and hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None
