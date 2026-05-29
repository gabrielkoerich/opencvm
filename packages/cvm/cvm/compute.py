"""Read facts from the store, compute fundamental indicators, persist them."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import indicators
from .db import Fact, Indicator, Shares, session
from .indicators import FactRow


def _shares_lookup(rows: list[Shares]) -> dict[str, float]:
    return {r.period: r.total for r in rows if r.total}


def _shares_for(period: str, by_period: dict[str, float]) -> float | None:
    if period in by_period:
        return by_period[period]
    earlier = [p for p in by_period if p <= period]
    return by_period[max(earlier)] if earlier else None


def compute_and_store(cd_cvm: int) -> int:
    """Recompute every (scope, period) indicator set for one company."""
    with session() as s:
        facts = list(s.execute(select(Fact).where(Fact.cd_cvm == cd_cvm)).scalars())
        shares_rows = list(
            s.execute(select(Shares).where(Shares.cd_cvm == cd_cvm)).scalars()
        )
        by_period = _shares_lookup(shares_rows)

        grouped: dict[tuple[str, str], list[FactRow]] = defaultdict(list)
        fiscal_year: dict[tuple[str, str], int] = {}
        for f in facts:
            key = (f.scope, f.period)
            grouped[key].append(
                FactRow(f.statement, f.account_code, f.account_desc, f.value)
            )
            fiscal_year[key] = f.fiscal_year

        rows: list[dict[str, object]] = []
        for (scope, period), frows in grouped.items():
            shares = _shares_for(period, by_period)
            values = indicators.compute_all(frows, shares)
            for name, value in values.items():
                rows.append(
                    {
                        "cd_cvm": cd_cvm,
                        "scope": scope,
                        "period": period,
                        "fiscal_year": fiscal_year[(scope, period)],
                        "name": name,
                        "value": None if value is None else float(value),
                    }
                )

        if not rows:
            return 0
        for i in range(0, len(rows), 5000):
            batch = rows[i : i + 5000]
            stmt = sqlite_insert(Indicator).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["cd_cvm", "scope", "period", "name"],
                set_={"value": stmt.excluded.value, "fiscal_year": stmt.excluded.fiscal_year},
            )
            s.execute(stmt)
    return len(rows)


def all_company_ids() -> list[int]:
    with session() as s:
        return list(s.execute(select(Fact.cd_cvm).distinct()).scalars())
