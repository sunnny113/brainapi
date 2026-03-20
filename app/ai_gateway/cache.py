from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class CacheItem:
    value: object
    expires_at: float


class TTLCache:
    """Simple in-memory TTL cache.

    This is process-local. In production with multiple replicas, use Redis.
    """

    def __init__(self, max_items: int = 1024, ttl_seconds: int = 60) -> None:
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, CacheItem] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [key for key, item in self._items.items() if item.expires_at <= now]
        for key in expired:
            self._items.pop(key, None)

    def get(self, key: str) -> object | None:
        self._purge_expired()
        item = self._items.get(key)
        if not item:
            return None
        if item.expires_at <= time.time():
            self._items.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: object) -> None:
        self._purge_expired()

        if len(self._items) >= self.max_items:
            # Best-effort eviction: remove an arbitrary item.
            first = next(iter(self._items.keys()), None)
            if first is not None:
                self._items.pop(first, None)

        self._items[key] = CacheItem(value=value, expires_at=time.time() + self.ttl_seconds)
