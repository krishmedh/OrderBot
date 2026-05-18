import json
import tempfile
from pathlib import Path

import pytest

from app.domain.models import Product
from app.services.catalog_vector_store import _keyword_fallback, search_catalog_context
from app.adapters.in_memory_repositories import InMemoryInventoryRepository
from app.services.inventory_service import InventoryService
from app.services.store_inventory_locator import StoreInventoryLocator


@pytest.fixture
def north_inventory() -> InventoryService:
    root = Path(tempfile.mkdtemp()) / "catalogs"
    root.mkdir(parents=True)
    catalog = [
        {"sku": "CLING-FILM", "name": "Cling wrap 30m", "quantity_available": 28, "price": 48.0},
        {"sku": "RICE-1KG", "name": "Rice 1kg", "quantity_available": 120, "price": 65.0},
        {"sku": "DAL-TOOR-1KG", "name": "Toor dal 1kg", "quantity_available": 55, "price": 118.0},
    ]
    (root / "north.json").write_text(json.dumps(catalog), encoding="utf-8")
    locator = StoreInventoryLocator(root, "default", fallback=InMemoryInventoryRepository())
    return InventoryService(locator)


def test_keyword_fallback_ranks_by_token_overlap() -> None:
    products = [
        Product("CLING-FILM", "Cling wrap 30m", 28, 48.0),
        Product("RICE-1KG", "Rice 1kg", 120, 65.0),
        Product("DAL-TOOR-1KG", "Toor dal 1kg", 55, 118.0),
    ]
    hits = _keyword_fallback(products, "cling wrap", 2)
    assert len(hits) == 1
    assert hits[0].sku == "CLING-FILM"


def test_search_catalog_context_without_api_key(north_inventory: InventoryService, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.catalog_vector_store.settings.catalog_vector_enabled",
        False,
    )
    monkeypatch.setattr(
        "app.services.catalog_vector_store.settings.openai_api_key",
        "",
    )
    ctx = search_catalog_context(north_inventory, "north", "toor dal")
    assert "Toor dal" in ctx
    assert "catalogue" in ctx.lower()
