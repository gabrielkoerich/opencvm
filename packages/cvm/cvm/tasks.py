"""Dramatiq actors: parse shards in parallel, compute indicators, back up.

Workers run with ``dramatiq cvm.tasks``. The Redis broker doubles as the queue
Laravel can push jobs to later. Backups are coalesced with a short-lived Redis
lock so a full backfill's many shards don't trigger a flood of S3 uploads.
"""

from __future__ import annotations

import dramatiq
import redis
from dramatiq.brokers.redis import RedisBroker

from . import backup, compute, config, ingest

broker = RedisBroker(url=config.REDIS_URL)
dramatiq.set_broker(broker)

_redis: redis.Redis = redis.Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
    config.REDIS_URL
)

_BACKUP_LOCK = "cvm:backup:lock"
_BACKUP_WINDOW = 300  # seconds: at most one backup per window during a backfill


@dramatiq.actor(max_retries=3)
def parse_dataset_year(dataset: str, year: int) -> None:
    ingest.ingest_dataset_year(dataset, year)
    enqueue_backup()


@dramatiq.actor(max_retries=3)
def parse_ipe(year: int) -> None:
    ingest.ingest_ipe(year)
    enqueue_backup()


@dramatiq.actor(max_retries=3)
def parse_cad() -> None:
    ingest.ingest_cad()


@dramatiq.actor(max_retries=2)
def compute_company(cd_cvm: int) -> None:
    compute.compute_and_store(cd_cvm)


@dramatiq.actor(max_retries=1)
def recompute_all() -> None:
    from .cache import bump_version

    for cd in compute.all_company_ids():
        compute_company.send(cd)
    bump_version()


@dramatiq.actor(max_retries=2, time_limit=600_000)
def backup_to_s3() -> None:
    # Coalesce: only one backup per window. Lock expiry (not release) debounces.
    if not _redis.set(_BACKUP_LOCK, "1", nx=True, ex=_BACKUP_WINDOW):
        return
    backup.backup_now(to_s3=True)


def enqueue_backup() -> None:
    backup_to_s3.send()
