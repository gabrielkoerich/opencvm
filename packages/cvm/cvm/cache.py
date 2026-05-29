"""Sync-version-keyed read cache.

CVM data is immutable once published, so reads only need invalidating when a sync
writes new data. Every sync bumps a monotonic ``version`` in ``sync_meta``; cached
entries carry the version they were built under and are recomputed when it moves.
The same version drives HTTP ``ETag`` / ``Cache-Control`` so clients (and Laravel)
can cache too.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

from .db import SyncMeta, session

_VERSION_KEY = "version"
_store: dict[str, tuple[int, object]] = {}

T = TypeVar("T")


def get_version() -> int:
    with session() as s:
        row = s.get(SyncMeta, _VERSION_KEY)
        return int(row.value) if row else 0


def bump_version() -> int:
    with session() as s:
        row = s.get(SyncMeta, _VERSION_KEY)
        new = (int(row.value) + 1) if row else 1
        if row:
            row.value = str(new)
        else:
            s.add(SyncMeta(key=_VERSION_KEY, value=str(new)))
    _store.clear()
    return new


def get_or_set(key: str, loader: Callable[[], T]) -> T:
    version = get_version()
    hit = _store.get(key)
    if hit is not None and hit[0] == version:
        return cast("T", hit[1])
    value = loader()
    _store[key] = (version, value)
    return value


def etag() -> str:
    return f'W/"v{get_version()}"'


def get_meta(key: str) -> str | None:
    with session() as s:
        row = s.get(SyncMeta, key)
        return row.value if row else None


def set_meta(key: str, value: str) -> None:
    with session() as s:
        row = s.get(SyncMeta, key)
        if row:
            row.value = value
        else:
            s.add(SyncMeta(key=key, value=value))
