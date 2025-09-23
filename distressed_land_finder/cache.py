from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_at: Optional[float]

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at < time.time()


class CacheManager:
    """Simple JSON-backed cache for HTTP sources."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: Dict[str, CacheEntry] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError:
                data = {}
            for key, payload in data.items():
                self._entries[key] = CacheEntry(
                    value=payload.get("value"),
                    expires_at=payload.get("expires_at"),
                )

    def get(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        if not entry:
            return None
        if entry.is_expired():
            del self._entries[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._entries[key] = CacheEntry(value=value, expires_at=expires_at)

    def save(self) -> None:
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized: Dict[str, Dict[str, Any]] = {}
        for key, entry in self._entries.items():
            expires_at: Optional[float]
            if entry.expires_at is None:
                expires_at = None
            else:
                expires_at = entry.expires_at
            serialized[key] = {
                "value": entry.value,
                "expires_at": expires_at,
            }
        self.path.write_text(json.dumps(serialized, indent=2, sort_keys=True))
