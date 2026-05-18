import hashlib
import hmac

from app.api.security import is_valid_whatsapp_signature


def test_signature_valid() -> None:
    secret = "my-secret"
    body = b'{"intent":"question"}'
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    header = f"sha256={digest}"
    assert is_valid_whatsapp_signature(secret, body, header)


def test_signature_invalid() -> None:
    assert not is_valid_whatsapp_signature("my-secret", b"abc", "sha256=wrong")
