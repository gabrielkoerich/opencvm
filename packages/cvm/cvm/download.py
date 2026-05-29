"""Cached, conditional downloader for CVM ZIPs / CSVs.

Each download remembers the server's ``ETag`` / ``Last-Modified`` next to the
file. Subsequent fetches send conditional headers, so unchanged shards return
``304`` and we reuse the cached copy — cheap enough to run daily over the whole
backfill.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import requests

from . import config
from .datasets import DATASETS, Dataset

_TIMEOUT = 120
_HEADERS = {"User-Agent": "bean-cvm/0.1 (+https://dados.cvm.gov.br)"}


def _meta_path(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".meta.json")


def _load_meta(target: Path) -> dict[str, str]:
    mp = _meta_path(target)
    if mp.exists():
        try:
            return cast("dict[str, str]", json.loads(mp.read_text()))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_meta(target: Path, meta: dict[str, str]) -> None:
    _meta_path(target).write_text(json.dumps(meta))


def fetch(url: str, target: Path) -> tuple[Path, bool]:
    """Download ``url`` to ``target`` unless unchanged. Returns (path, changed)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    meta = _load_meta(target)
    headers = dict(_HEADERS)
    if target.exists():
        if etag := meta.get("etag"):
            headers["If-None-Match"] = etag
        if last_mod := meta.get("last_modified"):
            headers["If-Modified-Since"] = last_mod

    resp = requests.get(url, headers=headers, timeout=_TIMEOUT, stream=True)
    if resp.status_code == 304 and target.exists():
        return target, False
    resp.raise_for_status()

    tmp = target.with_suffix(target.suffix + ".part")
    chunks = cast("Iterator[bytes]", resp.iter_content(chunk_size=1 << 16))
    with open(tmp, "wb") as fh:
        for chunk in chunks:
            fh.write(chunk)
    tmp.replace(target)

    new_meta: dict[str, str] = {}
    if etag := resp.headers.get("ETag"):
        new_meta["etag"] = etag
    if last_mod := resp.headers.get("Last-Modified"):
        new_meta["last_modified"] = last_mod
    _save_meta(target, new_meta)
    return target, True


def download_dataset(key: str, year: int | None = None) -> tuple[Path, bool]:
    """Fetch a dataset shard (ZIP or single CSV) into the download cache."""
    ds: Dataset = DATASETS[key]
    url = ds.url(year)
    name = Path(url).name
    sub = key if not ds.yearly else f"{key}/{year}"
    target = config.DOWNLOAD_DIR / sub / name
    return fetch(url, target)


def extract_member(zip_path: Path, member: str) -> Path | None:
    """Extract a single CSV from a cached ZIP next to it; returns the path or None."""
    out_dir = zip_path.with_suffix("")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / member
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if member not in zf.namelist():
                return None
            if not out.exists():
                zf.extract(member, out_dir)
    except (zipfile.BadZipFile, FileNotFoundError):
        return None
    return out if out.exists() else None
