"""In-Docker cron (APScheduler) — no host crontab needed.

Runs as its own compose service and only *enqueues* work onto Redis; the worker
pool does the heavy lifting. Schedule is configurable via env so the VPS needs
zero manual setup beyond ``docker compose up``.
"""

from __future__ import annotations

import logging
import os

from apscheduler.schedulers.blocking import (  # pyright: ignore[reportMissingTypeStubs]
    BlockingScheduler,
)
from apscheduler.triggers.cron import (  # pyright: ignore[reportMissingTypeStubs]
    CronTrigger,
)

from . import sync
from .backup import backup_now
from .db import init_db

log = logging.getLogger("cvm.scheduler")

# Defaults: daily incremental at 09:00, weekly full backfill Sun 04:00, nightly backup 03:00.
DAILY_HOUR = int(os.environ.get("CVM_DAILY_HOUR", "9"))
WEEKLY_FULL_DOW = os.environ.get("CVM_WEEKLY_FULL_DOW", "sun")
WEEKLY_FULL_HOUR = int(os.environ.get("CVM_WEEKLY_FULL_HOUR", "4"))
BACKUP_HOUR = int(os.environ.get("CVM_BACKUP_HOUR", "3"))


def _daily() -> None:
    log.info("daily incremental sync: enqueuing")
    sync.enqueue_sync(full=False)


def _weekly_full() -> None:
    log.info("weekly full backfill: enqueuing")
    sync.enqueue_sync(full=True)


def _nightly_backup() -> None:
    log.info("nightly backup: %s", backup_now(to_s3=True))


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(_daily, CronTrigger(hour=DAILY_HOUR, minute=0), id="daily")  # pyright: ignore[reportUnknownMemberType]
    scheduler.add_job(  # pyright: ignore[reportUnknownMemberType]
        _weekly_full,
        CronTrigger(day_of_week=WEEKLY_FULL_DOW, hour=WEEKLY_FULL_HOUR, minute=0),
        id="weekly_full",
    )
    scheduler.add_job(  # pyright: ignore[reportUnknownMemberType]
        _nightly_backup, CronTrigger(hour=BACKUP_HOUR, minute=0), id="backup"
    )
    log.info("scheduler started (daily=%dh, backup=%dh UTC)", DAILY_HOUR, BACKUP_HOUR)
    scheduler.start()  # pyright: ignore[reportUnknownMemberType]
