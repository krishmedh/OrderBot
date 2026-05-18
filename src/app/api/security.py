import hashlib
import hmac


def is_valid_whatsapp_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    if not secret:
        return True
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    given = signature_header.replace("sha256=", "", 1)
    return hmac.compare_digest(expected, given)
