"""Resolve product image URLs for chat UI and WhatsApp image messages."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from app.config import settings
from app.domain.models import Product

# Stable stock photos by SKU prefix (Unsplash CDN).
_PREFIX_IMAGES: dict[str, str] = {
    "MILK": "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=400&h=300&fit=crop",
    "SUGAR": "https://images.unsplash.com/photo-1581441363689-1f3e87f8adfb?w=400&h=300&fit=crop",
    "RICE": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=400&h=300&fit=crop",
    "ATTA": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=400&h=300&fit=crop",
    "DAL": "https://images.unsplash.com/photo-1584270354949-c26b0d416988?w=400&h=300&fit=crop",
    "SALT": "https://images.unsplash.com/photo-1609501676722-718812f77344?w=400&h=300&fit=crop",
    "TEA": "https://images.unsplash.com/photo-1564890369478-c89ca6d9cde9?w=400&h=300&fit=crop",
    "BISCUIT": "https://images.unsplash.com/photo-1558961363-fa8eabcc7586?w=400&h=300&fit=crop",
    "BREAD": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=400&h=300&fit=crop",
    "EGGS": "https://images.unsplash.com/photo-1582722877045-44dc416c8ae4?w=400&h=300&fit=crop",
    "BUTTER": "https://images.unsplash.com/photo-1589985270824-93b6bb4bf66e?w=400&h=300&fit=crop",
    "GHEE": "https://images.unsplash.com/photo-1628088062854-bb54f4c5b8c8?w=400&h=300&fit=crop",
    "HONEY": "https://images.unsplash.com/photo-1587049353266-1e71fcef9bb1?w=400&h=300&fit=crop",
    "OIL": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=400&h=300&fit=crop",
    "TURMERIC": "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?w=400&h=300&fit=crop",
    "CHILLI": "https://images.unsplash.com/photo-1606923829579-0b981e9e0b47?w=400&h=300&fit=crop",
    "CUMIN": "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=400&h=300&fit=crop",
    "CORIANDER": "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?w=400&h=300&fit=crop",
    "GARAM": "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=400&h=300&fit=crop",
    "PASTA": "https://images.unsplash.com/photo-1551462147-858ead2d3e3e?w=400&h=300&fit=crop",
    "NOODLES": "https://images.unsplash.com/photo-1612929649238-b2d8968f5c0e?w=400&h=300&fit=crop",
    "OATS": "https://images.unsplash.com/photo-1517673400267-025144f6360f?w=400&h=300&fit=crop",
    "SOYA": "https://images.unsplash.com/photo-1584270354949-c26b0d416988?w=400&h=300&fit=crop",
    "PAPAD": "https://images.unsplash.com/photo-1601050690597-df0565f5f0e4?w=400&h=300&fit=crop",
    "PICKLE": "https://images.unsplash.com/photo-1609501676722-718812f77344?w=400&h=300&fit=crop",
    "JAM": "https://images.unsplash.com/photo-1587049353266-1e71fcef9bb1?w=400&h=300&fit=crop",
    "PEANUT": "https://images.unsplash.com/photo-1587049353266-1e71fcef9bb1?w=400&h=300&fit=crop",
    "COFFEE": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=400&h=300&fit=crop",
    "HORLICKS": "https://images.unsplash.com/photo-1559492332-75052240d8f4?w=400&h=300&fit=crop",
    "CHOCOLATE": "https://images.unsplash.com/photo-1548907040-4baa42d10919?w=400&h=300&fit=crop",
    "CHIPS": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=400&h=300&fit=crop",
    "SOAP": "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?w=400&h=300&fit=crop",
    "SHAMPOO": "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?w=400&h=300&fit=crop",
    "TOOTHPASTE": "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?w=400&h=300&fit=crop",
    "TOOTHBRUSH": "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?w=400&h=300&fit=crop",
    "DETERGENT": "https://images.unsplash.com/photo-1585421514283-efb3c0c8b0e0?w=400&h=300&fit=crop",
    "DISHWASH": "https://images.unsplash.com/photo-1585421514283-efb3c0c8b0e0?w=400&h=300&fit=crop",
    "TISSUE": "https://images.unsplash.com/photo-1585421514283-efb3c0c8b0e0?w=400&h=300&fit=crop",
    "TOILET": "https://images.unsplash.com/photo-1585421514283-efb3c0c8b0e0?w=400&h=300&fit=crop",
    "SANITIZER": "https://images.unsplash.com/photo-1585421514283-efb3c0c8b0e0?w=400&h=300&fit=crop",
}

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
_catalog_images_dir: Path | None = None


def set_catalog_images_dir(path: Path) -> None:
    global _catalog_images_dir
    _catalog_images_dir = path


def catalog_images_dir() -> Path:
    global _catalog_images_dir
    if _catalog_images_dir is None:
        base = Path(settings.catalog_data_dir)
        if not base.is_absolute():
            base = Path.cwd() / base
        _catalog_images_dir = base / "images"
    return _catalog_images_dir


def public_base_url() -> str:
    return (settings.public_base_url or "http://127.0.0.1:8000").rstrip("/")


def to_absolute_url(url_or_path: str) -> str:
    u = (url_or_path or "").strip()
    if not u:
        return u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if not u.startswith("/"):
        u = "/" + u
    return f"{public_base_url()}{u}"


def _local_image_path(sku: str) -> Path | None:
    folder = catalog_images_dir()
    if not folder.is_dir():
        return None
    stem = sku.upper()
    for ext in _IMAGE_EXTENSIONS:
        candidate = folder / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _prefix_fallback_url(sku: str) -> str:
    key = sku.upper().split("-", 1)[0]
    if key in _PREFIX_IMAGES:
        return _PREFIX_IMAGES[key]
    return f"https://picsum.photos/seed/{quote(sku.upper())}/400/300"


def resolve_product_image(product: Product) -> str:
    if product.image_url:
        return to_absolute_url(product.image_url)

    local = _local_image_path(product.sku)
    if local:
        return to_absolute_url(f"/catalog/images/{local.name}")

    return _prefix_fallback_url(product.sku)


def product_image_attachments(
    products: list[Product],
    *,
    max_count: int = 6,
    currency: str | None = None,
) -> list[dict[str, str]]:
    cur = currency or settings.default_currency
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for p in products:
        if p.sku in seen:
            continue
        seen.add(p.sku)
        out.append(
            {
                "sku": p.sku,
                "url": resolve_product_image(p),
                "caption": f"{p.name} — {p.price:.2f} {cur}",
            }
        )
        if len(out) >= max_count:
            break
    return out
