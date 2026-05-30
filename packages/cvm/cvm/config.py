"""Runtime configuration, all overridable via environment variables.

Single source of truth for paths and service URLs so the CLI, workers and API
all agree on where the SQLite file, download cache and Redis broker live.
"""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    return Path(os.environ.get("CVM_DATA_DIR", _PKG_ROOT / "data")).resolve()


DATA_DIR: Path = _data_dir()
DOWNLOAD_DIR: Path = DATA_DIR / "downloads"
BACKUP_DIR: Path = DATA_DIR / "backups"

DB_PATH: Path = Path(os.environ.get("CVM_DB_PATH", DATA_DIR / "cvm.sqlite")).resolve()
DB_URL: str = os.environ.get("CVM_DB_URL", f"sqlite:///{DB_PATH}")

REDIS_URL: str = os.environ.get("CVM_REDIS_URL", "redis://localhost:6379/0")

# How many timestamped backups to keep before rotating out the oldest.
BACKUP_KEEP: int = int(os.environ.get("CVM_BACKUP_KEEP", "14"))

# S3 (or S3-compatible: R2, MinIO) offsite backup. Empty bucket disables upload.
S3_BUCKET: str = os.environ.get("CVM_S3_BUCKET", "")
S3_PREFIX: str = os.environ.get("CVM_S3_PREFIX", "cvm-backups")
S3_ENDPOINT: str = os.environ.get("CVM_S3_ENDPOINT", "")  # for R2/MinIO

# brapi token (live prices); read lazily by callers that need it.
BRAPI_TOKEN: str = os.environ.get("BRAPI_API_KEY", "")

# Global API rate limit (slowapi syntax: "<n>/<window>"). Override per-deploy.
RATE_LIMIT: str = os.environ.get("CVM_RATE_LIMIT", "60/minute")

# CORS — comma-separated list of allowed origins. Use "*" for full open.
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.environ.get("CVM_CORS_ORIGINS", "*").split(",") if o.strip()
]


def ensure_dirs() -> None:
    for d in (DATA_DIR, DOWNLOAD_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)
