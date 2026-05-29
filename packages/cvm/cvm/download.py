"""Disk-frugal downloader for CVM ZIPs / CSVs.

Each shard is fetched into a throwaway temp dir, parsed, then deleted — nothing
is cached between syncs. Peak disk usage stays at a single shard (plus the CSV
currently being parsed) instead of hoarding the entire multi-year backfill.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import requests

from .datasets import DATASETS

_TIMEOUT = 120
_HEADERS = {"User-Agent": "bean-cvm/0.1 (+https://dados.cvm.gov.br)"}


def _download_to(url: str, target: Path) -> None:
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, stream=True)
    resp.raise_for_status()
    chunks = cast("Iterator[bytes]", resp.iter_content(chunk_size=1 << 16))
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            for chunk in chunks:
                fh.write(chunk)
        tmp.replace(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@contextmanager
def temp_dataset(key: str, year: int | None = None) -> Iterator[Path]:
    """Download a dataset shard into a temp dir; delete the whole dir on exit."""
    url = DATASETS[key].url(year)
    tmpdir = Path(tempfile.mkdtemp(prefix="cvm-dl-"))
    target = tmpdir / Path(url).name
    try:
        _download_to(url, target)
        yield target
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def extract_member(zip_path: Path, member: str) -> Path | None:
    """Extract a single CSV from a ZIP next to it; returns the path or None."""
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
