"""Sync orchestration: full backfill + daily incremental.

Two execution paths share the same work definition:
  * ``enqueue_*`` pushes shards onto Redis for the Docker worker pool (production);
  * ``run_inline`` does everything in-process (handy for CLI verification / no broker).
"""

from __future__ import annotations

from datetime import date

from . import compute, ingest
from .cache import bump_version, set_meta
from .datasets import DATASETS, FINANCIAL_DATASETS, SCOPES, STATEMENTS


def _financial_years(full: bool, through: int) -> dict[str, list[int]]:
    if full:
        return {k: DATASETS[k].years(through) for k in FINANCIAL_DATASETS}
    return {k: [through] for k in FINANCIAL_DATASETS}


def _ipe_years(full: bool, through: int) -> list[int]:
    return DATASETS["ipe"].years(through) if full else [through]


# --- enqueue mode (production: Docker workers) --------------------------------


def enqueue_sync(full: bool = False, through: int | None = None) -> int:
    """Push all sync work onto Redis. Returns number of messages enqueued."""
    from . import tasks  # imported here so CLI paths without Redis still load

    through = through or date.today().year
    n = 0

    tasks.parse_cad.send()
    n += 1

    for key, years in _financial_years(full, through).items():
        for year in years:
            tasks.parse_shares.send(key, year)
            n += 1
            for statement in STATEMENTS:
                for scope in SCOPES:
                    tasks.parse_statement_shard.send(key, statement, scope, year)
                    n += 1

    for year in _ipe_years(full, through):
        tasks.parse_ipe.send(year)
        n += 1

    tasks.recompute_all.send()
    n += 1
    set_meta("last_sync", date.today().isoformat())
    return n


# --- inline mode (no broker) --------------------------------------------------


def run_inline(full: bool = False, through: int | None = None) -> dict[str, int]:
    through = through or date.today().year
    counts = {"cad": 0, "facts": 0, "shares": 0, "ipe": 0, "companies": 0}

    counts["cad"] = ingest.ingest_cad()

    for key, years in _financial_years(full, through).items():
        for year in years:
            for statement in STATEMENTS:
                for scope in SCOPES:
                    counts["facts"] += ingest.ingest_statement(
                        key, statement, scope, year
                    )
            counts["shares"] += ingest.ingest_shares(key, year)

    for year in _ipe_years(full, through):
        counts["ipe"] += ingest.ingest_ipe(year)

    for cd in compute.all_company_ids():
        compute.compute_and_store(cd)
        counts["companies"] += 1

    bump_version()
    set_meta("last_sync", date.today().isoformat())
    return counts
