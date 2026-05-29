"""SQLite backups: consistent snapshot + offsite S3 upload + local rotation.

``VACUUM INTO`` produces a transactionally-consistent copy even while workers are
writing (WAL-safe), so this is safe to call after parse jobs. If no S3 bucket is
configured, only the local snapshot is kept.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config


def snapshot() -> Path | None:
    """Write a consistent copy of the DB to the backup dir; return its path."""
    if not config.DB_PATH.exists():
        return None
    config.ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = config.BACKUP_DIR / f"cvm-{stamp}.sqlite"
    con = sqlite3.connect(str(config.DB_PATH))
    try:
        con.execute("VACUUM INTO ?", (str(dest),))
    finally:
        con.close()
    return dest


def rotate(keep: int | None = None) -> int:
    """Keep the newest ``keep`` local snapshots; remove older ones."""
    keep = config.BACKUP_KEEP if keep is None else keep
    snaps = sorted(config.BACKUP_DIR.glob("cvm-*.sqlite"))
    removed = 0
    for old in snaps[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
        removed += 1
    return removed


def upload_s3(path: Path) -> str | None:
    """Upload a snapshot to S3 (or S3-compatible). Returns the key, or None."""
    if not config.S3_BUCKET:
        return None
    import boto3  # pyright: ignore[reportMissingTypeStubs]  # lazy, optional at runtime

    client_kwargs: dict[str, str] = {}
    if config.S3_ENDPOINT:
        client_kwargs["endpoint_url"] = config.S3_ENDPOINT
    s3 = boto3.client("s3", **client_kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    key = f"{config.S3_PREFIX.rstrip('/')}/{path.name}"
    s3.upload_file(str(path), config.S3_BUCKET, key)  # pyright: ignore[reportUnknownMemberType]
    return key


def backup_now(to_s3: bool = True) -> dict[str, object]:
    snap = snapshot()
    if snap is None:
        return {"snapshot": None, "uploaded": None, "rotated": 0}
    key = upload_s3(snap) if to_s3 else None
    rotated = rotate()
    return {"snapshot": str(snap), "uploaded": key, "rotated": rotated}
