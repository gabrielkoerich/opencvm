"""Read facts from the store, compute fundamental indicators, persist them.

Indicators are computed for two frequencies:
  * quarterly (``period_months == 3``) — standalone-quarter flow + the quarter-end
    balance sheet. CVM ships no Q4 ITR, so the standalone Q4 is *derived* here as
    ``annual (DFP) - (Q1 + Q2 + Q3)`` and stored back as 3-month facts at Dec-31.
  * annual (``period_months == 12``) — full-year flow + the year-end balance sheet.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import indicators
from .db import Fact, Indicator, Shares, session
from .indicators import FactRow

_Q_ENDS = frozenset({"03-31", "06-30", "09-30"})


def _shares_lookup(rows: list[Shares]) -> dict[str, float]:
    return {r.period: r.total for r in rows if r.total}


def _shares_for(period: str, by_period: dict[str, float]) -> float | None:
    if period in by_period:
        return by_period[period]
    earlier = [p for p in by_period if p <= period]
    return by_period[max(earlier)] if earlier else None


def _derive_q4_rows(cd_cvm: int, facts: list[Fact]) -> list[dict[str, object]]:
    """Standalone Q4 = full-year flow minus the three reported quarters."""
    annual: dict[tuple[str, int, str, str], tuple[float, str]] = {}
    qsum: dict[tuple[str, int, str, str], float] = defaultdict(float)
    qseen: dict[tuple[str, int, str, str], set[str]] = defaultdict(set)
    for f in facts:
        key = (f.scope, f.fiscal_year, f.statement, f.account_code)
        if f.period_months == 12 and f.period.endswith("-12-31"):
            annual[key] = (f.value, f.account_desc)
        elif f.period_months == 3 and f.period[5:] in _Q_ENDS:
            qsum[key] += f.value
            qseen[key].add(f.period[5:])

    rows: list[dict[str, object]] = []
    for (scope, year, statement, code), (annual_val, desc) in annual.items():
        key = (scope, year, statement, code)
        if len(qseen[key]) != len(_Q_ENDS):  # need all three quarters to back out Q4
            continue
        rows.append(
            {
                "cd_cvm": cd_cvm,
                "dataset": "derived",
                "statement": statement,
                "scope": scope,
                "period": f"{year}-12-31",
                "period_months": 3,
                "fiscal_year": year,
                "account_code": code,
                "account_desc": desc,
                "value": float(annual_val - qsum[key]),
                "version": 0,
            }
        )
    return rows


def _store_facts(session_: Session, rows: list[dict[str, object]]) -> None:
    for i in range(0, len(rows), 5000):
        batch = rows[i : i + 5000]
        stmt = sqlite_insert(Fact).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                "cd_cvm",
                "statement",
                "scope",
                "period",
                "period_months",
                "account_code",
            ],
            set_={
                c: getattr(stmt.excluded, c)
                for c in ("value", "version", "account_desc", "fiscal_year", "dataset")
            },
        )
        session_.execute(stmt)


def compute_and_store(cd_cvm: int) -> int:
    """Recompute every (scope, period, frequency) indicator set for one company."""
    with session() as s:
        facts = list(s.execute(select(Fact).where(Fact.cd_cvm == cd_cvm)).scalars())
        shares_rows = list(
            s.execute(select(Shares).where(Shares.cd_cvm == cd_cvm)).scalars()
        )
        by_period = _shares_lookup(shares_rows)

        q4_rows = _derive_q4_rows(cd_cvm, facts)
        if q4_rows:
            _store_facts(s, q4_rows)

        # Split point-in-time balances (months 0) from flow spans (3 / 12), then
        # build each indicator set from a frequency's flow plus the period balance.
        stock: dict[tuple[str, str], list[FactRow]] = defaultdict(list)
        flow: dict[tuple[str, str, int], list[FactRow]] = defaultdict(list)
        fiscal_year: dict[tuple[str, str], int] = {}

        def add(scope: str, period: str, months: int, fy: int, fr: FactRow) -> None:
            fiscal_year[(scope, period)] = fy
            if months == 0:
                stock[(scope, period)].append(fr)
            else:
                flow[(scope, period, months)].append(fr)

        for f in facts:
            add(
                f.scope,
                f.period,
                f.period_months,
                f.fiscal_year,
                FactRow(f.statement, f.account_code, f.account_desc, f.value),
            )
        for r in q4_rows:
            add(
                str(r["scope"]),
                str(r["period"]),
                int(str(r["period_months"])),
                int(str(r["fiscal_year"])),
                FactRow(
                    str(r["statement"]),
                    str(r["account_code"]),
                    str(r["account_desc"]),
                    float(str(r["value"])),
                ),
            )

        rows: list[dict[str, object]] = []
        for (scope, period, months), frows in flow.items():
            combined = frows + stock.get((scope, period), [])
            shares = _shares_for(period, by_period)
            values = indicators.compute_all(combined, shares)
            for name, value in values.items():
                rows.append(
                    {
                        "cd_cvm": cd_cvm,
                        "scope": scope,
                        "period": period,
                        "period_months": months,
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
                index_elements=["cd_cvm", "scope", "period", "period_months", "name"],
                set_={
                    "value": stmt.excluded.value,
                    "fiscal_year": stmt.excluded.fiscal_year,
                },
            )
            s.execute(stmt)
    return len(rows)


def all_company_ids() -> list[int]:
    with session() as s:
        return list(s.execute(select(Fact.cd_cvm).distinct()).scalars())
