"""Per-store inventory loaded from ``{catalog_dir}/{store_id}.json``."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.interfaces import InventoryRepository
from app.domain.models import Product


class EmptyInventoryRepository(InventoryRepository):
    """No products (missing catalog file for a store)."""

    def get_product(self, sku: str) -> Product | None:
        return None

    def update_stock(self, sku: str, delta: int) -> None:
        raise ValueError(f"Unknown product: {sku}")

    def list_products(self) -> list[Product]:
        return []


class JsonCatalogInventoryRepository(InventoryRepository):
    """Load products from a JSON file; stock updates stay in memory for this process."""

    def __init__(self, catalog_path: Path) -> None:
        self._path = catalog_path
        self._products: dict[str, Product] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"Catalog {self._path} must be a JSON array of items.")
        for row in raw:
            if not isinstance(row, dict):
                continue
            sku = str(row["sku"]).strip()
            name = str(row.get("name", sku)).strip()
            qty = int(row.get("quantity_available", row.get("quantity", 0)))
            price = float(row.get("price", 0.0))
            image_raw = (row.get("image_url") or row.get("image") or "").strip()
            image_url = image_raw or None
            self._products[sku.upper()] = Product(
                sku=sku.upper(),
                name=name,
                quantity_available=qty,
                price=price,
                image_url=image_url,
            )

    def get_product(self, sku: str) -> Product | None:
        return self._products.get(sku.upper())

    def update_stock(self, sku: str, delta: int) -> None:
        key = sku.upper()
        product = self._products.get(key)
        if not product:
            raise ValueError(f"Unknown product: {sku}")
        product.quantity_available += delta

    def list_products(self) -> list[Product]:
        return list(self._products.values())
