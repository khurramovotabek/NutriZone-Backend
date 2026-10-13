"""
Query Application Services: GetInventory, ListInventory, SearchInventory,
AdminListInventory.
"""
from __future__ import annotations

from apps.inventory.application.ports import InventoryRepository, InventorySearchGateway
from apps.inventory.domain.aggregates import Inventory
from apps.inventory.domain.enums import InventoryStatus
from common.exceptions import ResourceNotFound


class GetInventory:
    def __init__(self, repo: InventoryRepository) -> None:
        self._repo = repo

    def execute(self, code: str) -> Inventory:
        inventory = self._repo.get_by_code(code)
        if inventory is None or inventory.status == InventoryStatus.ARCHIVED:
            raise ResourceNotFound("Inventory not found.")
        return inventory


class ListInventory:
    def __init__(self, repo: InventoryRepository) -> None:
        self._repo = repo

    def execute(self, page: int = 1, page_size: int = 20) -> tuple[list[Inventory], int]:
        return self._repo.list_for_admin(status=InventoryStatus.ACTIVE.value, query=None, page=page, page_size=page_size)


class AdminListInventory:
    def __init__(self, repo: InventoryRepository) -> None:
        self._repo = repo

    def execute(self, status: str | None = None, query: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[Inventory], int]:
        return self._repo.list_for_admin(status=status, query=query, page=page, page_size=page_size)


class SearchInventory:
    def __init__(self, search_gateway: InventorySearchGateway) -> None:
        self._search_gateway = search_gateway

    def execute(self, query: str, filters: dict, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        return self._search_gateway.search(query=query, filters=filters, page=page, page_size=page_size)
