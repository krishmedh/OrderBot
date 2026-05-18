from pathlib import Path

from app.domain.models import Product
from app.services.product_media import (
    product_image_attachments,
    resolve_product_image,
    set_catalog_images_dir,
    to_absolute_url,
)


def test_resolve_uses_explicit_image_url() -> None:
    p = Product("SUGAR-1KG", "Sugar 1kg", 10, 45.0, image_url="https://cdn.example/sugar.jpg")
    assert resolve_product_image(p) == "https://cdn.example/sugar.jpg"


def test_resolve_prefix_fallback() -> None:
    p = Product("DAL-MOONG-1KG", "Moong dal 1kg", 10, 105.0)
    url = resolve_product_image(p)
    assert url.startswith("https://")


def test_local_catalog_image(tmp_path: Path) -> None:
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    (img_dir / "SUGAR-1KG.jpg").write_bytes(b"x")
    set_catalog_images_dir(img_dir)
    p = Product("SUGAR-1KG", "Sugar 1kg", 10, 45.0)
    assert "/catalog/images/SUGAR-1KG.jpg" in resolve_product_image(p)


def test_product_image_attachments_caps_count() -> None:
    products = [Product(f"SKU-{i}", f"Item {i}", 1, 1.0) for i in range(10)]
    out = product_image_attachments(products, max_count=3)
    assert len(out) == 3
    assert out[0]["sku"] == "SKU-0"
    assert "url" in out[0]


def test_to_absolute_url() -> None:
    assert to_absolute_url("/catalog/images/x.jpg").endswith("/catalog/images/x.jpg")
