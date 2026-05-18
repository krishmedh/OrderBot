"""Resolve per-store inventory repositories (JSON catalog per ``store_id``)."""

from __future__ import annotations

from pathlib import Path

from app.adapters.json_catalog_repository import EmptyInventoryRepository, JsonCatalogInventoryRepository
from app.domain.interfaces import InventoryRepository


class StoreInventoryLocator:
    """
    One repository instance per ``store_id`` (cached).

    If ``{catalog_dir}/{store_id}.json`` exists, load it. Else if ``store_id`` equals
    ``default_store_id`` and a ``fallback`` repo is set, use that (dev/tests). Otherwise empty.

    When ``prefer_database_inventory`` is True (e.g. ``DATABASE_URL`` is set), the
    ``default_store_id`` always uses ``fallback`` so SQL/global inventory stays authoritative.
    """

    def __init__(
        self,
        catalog_dir: Path,
        default_store_id: str,
        fallback: InventoryRepository | None = None,
        *,
        prefer_database_inventory: bool = False,
    ) -> None:
        self._catalog_dir = catalog_dir
        self._default_store_id = default_store_id
        self._fallback = fallback
        self._prefer_database_inventory = prefer_database_inventory
        self._cache: dict[str, InventoryRepository] = {}

    def catalog_path(self, store_id: str) -> Path:
        return self._catalog_dir / f"{store_id}.json"

    def get(self, store_id: str | None) -> InventoryRepository:
        sid = (store_id or self._default_store_id).strip() or self._default_store_id
        if sid not in self._cache:
            if self._prefer_database_inventory and sid == self._default_store_id and self._fallback is not None:
                self._cache[sid] = self._fallback
            else:
                path = self.catalog_path(sid)
                if path.is_file():
                    self._cache[sid] = JsonCatalogInventoryRepository(path)
                elif sid == self._default_store_id and self._fallback is not None:
                    self._cache[sid] = self._fallback
                else:
                    self._cache[sid] = EmptyInventoryRepository()
        return self._cache[sid]
