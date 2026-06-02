"""Render the entire read API to a static JSON tree for CDN serving.

The output mirrors the FastAPI paths under ``/v1/`` so a frontend can swap the
API base URL and nothing else:

    /v1/version.json
    /v1/companies/index.json
    /v1/companies/{cd_cvm}/index.json
    /v1/companies/{cd_cvm}/statements-{stmt}-{scope}-{freq}.json
    /v1/companies/{cd_cvm}/indicators-{scope}-{freq}.json
    /v1/companies/{cd_cvm}/documents.json
    /v1/tickers/index.json
    /v1/screen-{scope}-{freq}.json

A top-level ``manifest.json`` records the sync version + file/byte counts.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql import ColumnElement

from . import cache
from .db import Company, Document, Fact, Indicator, Ticker, session

_SCOPES = ("con", "ind")
_FREQS = ("annual", "quarterly")
_STATEMENTS = ("DRE", "BPA", "BPP")
_FREQ_MONTHS = {"quarterly": 3, "annual": 12}
_SCREEN_FIELDS = {
    "revenue", "ebit", "ebitda", "net_income", "equity", "net_debt",
    "gross_margin", "operating_margin", "net_margin", "ebitda_margin",
    "roe", "roa", "roic", "debt_to_equity", "current_ratio",
}


def _months_for(freq: str) -> int:
    return _FREQ_MONTHS[freq]


def _period_clause(freq: str) -> ColumnElement[bool]:
    m = _months_for(freq)
    if freq == "quarterly":
        return Fact.period_months.in_([m, 0])
    return or_(
        Fact.period_months == m,
        and_(Fact.period_months == 0, Fact.period.like("%-12-31")),
    )


def _pct(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None or prev == 0:
        return None
    return (curr - prev) / abs(prev)


def _growth(
    periods: dict[str, dict[str, float | None]], include_qoq: bool
) -> dict[str, dict[str, dict[str, float | None]]]:
    ordered = sorted(periods)
    out: dict[str, dict[str, dict[str, float | None]]] = {}
    for i, period in enumerate(ordered):
        prev = ordered[i - 1] if i > 0 else None
        yoy_key = f"{int(period[:4]) - 1}{period[4:]}"
        row: dict[str, dict[str, float | None]] = {}
        for name, val in periods[period].items():
            qoq = (
                _pct(val, periods[prev].get(name))
                if include_qoq and prev is not None
                else None
            )
            yoy = _pct(val, periods[yoy_key].get(name)) if yoy_key in periods else None
            row[name] = {"qoq": qoq, "yoy": yoy}
        out[period] = row
    return out


def _write_json(path: Path, payload: object) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, separators=(",", ":"), default=str).encode()
    path.write_bytes(data)
    return len(data)


def render_all(out: Path) -> dict[str, object]:
    """Render the full v1 tree under ``out``. Returns the manifest dict."""
    v1 = out / "v1"
    v1.mkdir(parents=True, exist_ok=True)

    files = 0
    bytes_total = 0

    version = cache.get_version()
    last_sync = cache.get_meta("last_sync")
    bytes_total += _write_json(
        v1 / "version.json", {"version": version, "last_sync": last_sync}
    )
    files += 1

    with session() as s:
        companies = list(
            s.execute(select(Company).order_by(Company.name)).scalars()
        )

        bytes_total += _write_json(
            v1 / "companies" / "index.json",
            [
                {
                    "cd_cvm": c.cd_cvm,
                    "name": c.name,
                    "sector": c.sector,
                    "tickers": [t.ticker for t in c.tickers],
                }
                for c in companies
            ],
        )
        files += 1

        all_tickers = list(s.execute(select(Ticker)).scalars())
        bytes_total += _write_json(
            v1 / "tickers" / "index.json",
            {t.ticker: {"cd_cvm": t.cd_cvm, "kind": t.kind} for t in all_tickers},
        )
        files += 1

        for ix, c in enumerate(companies, 1):
            cdir = v1 / "companies" / str(c.cd_cvm)

            bytes_total += _write_json(
                cdir / "index.json",
                {
                    "cd_cvm": c.cd_cvm,
                    "name": c.name,
                    "cnpj": c.cnpj,
                    "sector": c.sector,
                    "situation": c.situation,
                    "tickers": [
                        {"ticker": t.ticker, "kind": t.kind} for t in c.tickers
                    ],
                },
            )
            files += 1

            for stmt in _STATEMENTS:
                for scope in _SCOPES:
                    for freq in _FREQS:
                        rows = list(
                            s.execute(
                                select(Fact)
                                .where(
                                    Fact.cd_cvm == c.cd_cvm,
                                    Fact.statement == stmt,
                                    Fact.scope == scope,
                                    _period_clause(freq),
                                )
                                .order_by(Fact.period.desc(), Fact.account_code)
                            ).scalars()
                        )
                        if not rows:
                            continue
                        bytes_total += _write_json(
                            cdir / f"statements-{stmt}-{scope}-{freq}.json",
                            [
                                {
                                    "period": r.period,
                                    "account_code": r.account_code,
                                    "account_desc": r.account_desc,
                                    "value": r.value,
                                }
                                for r in rows
                            ],
                        )
                        files += 1

            for scope in _SCOPES:
                for freq in _FREQS:
                    months = _months_for(freq)
                    rows = list(
                        s.execute(
                            select(Indicator)
                            .where(
                                Indicator.cd_cvm == c.cd_cvm,
                                Indicator.scope == scope,
                                Indicator.period_months == months,
                            )
                            .order_by(Indicator.period.desc(), Indicator.name)
                        ).scalars()
                    )
                    if not rows:
                        continue
                    by_period: dict[str, dict[str, float | None]] = {}
                    for r in rows:
                        by_period.setdefault(r.period, {})[r.name] = r.value
                    growth = _growth(by_period, include_qoq=(freq == "quarterly"))
                    bytes_total += _write_json(
                        cdir / f"indicators-{scope}-{freq}.json",
                        {
                            "cd_cvm": c.cd_cvm,
                            "scope": scope,
                            "freq": freq,
                            "periods": by_period,
                            "growth": growth,
                        },
                    )
                    files += 1

            docs = list(
                s.execute(
                    select(Document)
                    .where(Document.cd_cvm == c.cd_cvm)
                    .order_by(Document.deliver_date.desc())
                    .limit(500)
                ).scalars()
            )
            if docs:
                bytes_total += _write_json(
                    cdir / "documents.json",
                    [
                        {
                            "category": d.category,
                            "type": d.doc_type,
                            "subject": d.subject,
                            "ref_date": d.ref_date,
                            "deliver_date": d.deliver_date,
                            "url": d.url,
                        }
                        for d in docs
                    ],
                )
                files += 1

            if ix % 50 == 0:
                print(f"  ... {ix}/{len(companies)} companies", flush=True)

        for scope in _SCOPES:
            for freq in _FREQS:
                months = _months_for(freq)
                latest = (
                    select(Indicator.cd_cvm, func.max(Indicator.period).label("period"))
                    .where(Indicator.scope == scope, Indicator.period_months == months)
                    .group_by(Indicator.cd_cvm)
                    .subquery()
                )
                rows = s.execute(
                    select(
                        Ticker.ticker,
                        Ticker.kind,
                        Company.cd_cvm,
                        Company.name,
                        Company.sector,
                        Indicator.period,
                        Indicator.name,
                        Indicator.value,
                    )
                    .join(Company, Company.cd_cvm == Ticker.cd_cvm)
                    .join(latest, latest.c.cd_cvm == Company.cd_cvm)
                    .join(
                        Indicator,
                        and_(
                            Indicator.cd_cvm == Company.cd_cvm,
                            Indicator.period == latest.c.period,
                            Indicator.scope == scope,
                            Indicator.period_months == months,
                        ),
                    )
                    .where(Indicator.name.in_(_SCREEN_FIELDS))
                    .order_by(Ticker.ticker)
                ).all()
                typed_rows = cast(
                    list[
                        tuple[
                            str, str | None, int, str, str | None, str, str, float | None
                        ]
                    ],
                    rows,
                )
                by_ticker: dict[str, dict[str, object]] = {}
                for ticker, kind, cd_cvm, name, sector, period, ind_name, value in typed_rows:
                    slot = by_ticker.setdefault(
                        ticker,
                        {
                            "ticker": ticker,
                            "kind": kind,
                            "cd_cvm": cd_cvm,
                            "name": name,
                            "sector": sector,
                            "period": period,
                        },
                    )
                    slot[ind_name] = value
                bytes_total += _write_json(
                    v1 / f"screen-{scope}-{freq}.json", list(by_ticker.values())
                )
                files += 1

    manifest: dict[str, object] = {
        "version": version,
        "last_sync": last_sync,
        "generated_at": int(time.time()),
        "files": files,
        "bytes": bytes_total,
    }
    _write_json(out / "manifest.json", manifest)
    print(
        f"rendered {files} files, {bytes_total / 1e6:.1f} MB → {out}",
        flush=True,
    )
    return manifest
