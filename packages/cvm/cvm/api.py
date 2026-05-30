"""FastAPI read API over the CVM store.

Responses carry a sync-version ``ETag`` + ``Cache-Control`` so clients (and the
Laravel frontend) can cache aggressively; CVM data only changes when a sync runs.
Price-based ratios are computed on demand from an injected ``price`` query param,
since prices come from a live source (brapi), not CVM.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import ColumnElement, and_, func, or_, select

from . import cache, config, indicators
from .db import Company, Document, Fact, Indicator, Shares, Ticker, session
from .indicators import FactRow

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[config.RATE_LIMIT],
    storage_uri=config.REDIS_URL,
)
app = FastAPI(title="OpenCVM", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

JSONDict = dict[str, object]
JSONList = list[dict[str, object]]

_FREQ_MONTHS = {"quarterly": 3, "annual": 12}


def _months_for(freq: str) -> int:
    return _FREQ_MONTHS.get(freq, 12)


def _period_clause(freq: str) -> ColumnElement[bool]:
    """Match flow rows for the frequency plus the relevant balance snapshots.

    Balance sheets are always point-in-time (``period_months == 0``); under the
    annual view only year-end snapshots are kept, quarterly keeps every quarter.
    """
    months = _months_for(freq)
    if freq == "quarterly":
        return Fact.period_months.in_([months, 0])
    return or_(
        Fact.period_months == months,
        and_(Fact.period_months == 0, Fact.period.like("%-12-31")),
    )


def _pct(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None or prev == 0:
        return None
    return (curr - prev) / abs(prev)


def _growth(
    periods: dict[str, dict[str, float | None]], include_qoq: bool
) -> dict[str, dict[str, dict[str, float | None]]]:
    """Per-period QoQ (previous period) and YoY (same period, prior year) %."""
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


def _cache_headers(request: Request, response: Response) -> Response | None:
    tag = cache.etag()
    response.headers["ETag"] = tag
    response.headers["Cache-Control"] = "public, max-age=300"
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag})
    return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> JSONDict:
    return {"version": cache.get_version(), "last_sync": cache.get_meta("last_sync")}


@app.get("/companies", response_model=None)
def companies(
    request: Request,
    response: Response,
    q: str | None = None,
    limit: Annotated[int, Query(le=500)] = 50,
    offset: int = 0,
) -> JSONList | Response:
    if (cached := _cache_headers(request, response)) is not None:
        return cached

    def load() -> JSONList:
        with session() as s:
            stmt = select(Company)
            if q:
                like = f"%{q.upper()}%"
                stmt = stmt.where(func.upper(Company.name).like(like))
            stmt = stmt.order_by(Company.name).limit(limit).offset(offset)
            return [
                {
                    "cd_cvm": c.cd_cvm,
                    "name": c.name,
                    "sector": c.sector,
                    "tickers": [t.ticker for t in c.tickers],
                }
                for c in s.execute(stmt).scalars()
            ]

    return cache.get_or_set(f"companies:{q}:{limit}:{offset}", load)


@app.get("/companies/{cd_cvm}", response_model=None)
def company_detail(
    cd_cvm: int, request: Request, response: Response
) -> JSONDict | Response:
    if (cached := _cache_headers(request, response)) is not None:
        return cached
    with session() as s:
        c = s.get(Company, cd_cvm)
        if c is None:
            response.status_code = 404
            return {"error": "not found"}
        return {
            "cd_cvm": c.cd_cvm,
            "name": c.name,
            "cnpj": c.cnpj,
            "sector": c.sector,
            "situation": c.situation,
            "tickers": [
                {"ticker": t.ticker, "kind": t.kind} for t in c.tickers
            ],
        }


@app.get("/companies/{cd_cvm}/statements", response_model=None)
def statements(
    cd_cvm: int,
    request: Request,
    response: Response,
    statement: str = "DRE",
    scope: str = "con",
    freq: str = "annual",
    year: int | None = None,
) -> JSONList | Response:
    if (cached := _cache_headers(request, response)) is not None:
        return cached
    with session() as s:
        stmt = select(Fact).where(
            Fact.cd_cvm == cd_cvm,
            Fact.statement == statement,
            Fact.scope == scope,
            _period_clause(freq),
        )
        if year:
            stmt = stmt.where(Fact.fiscal_year == year)
        stmt = stmt.order_by(Fact.period.desc(), Fact.account_code)
        return [
            {
                "period": f.period,
                "account_code": f.account_code,
                "account_desc": f.account_desc,
                "value": f.value,
            }
            for f in s.execute(stmt).scalars()
        ]


@app.get("/companies/{cd_cvm}/account/{code}", response_model=None)
def account_series(
    cd_cvm: int,
    code: str,
    request: Request,
    response: Response,
    scope: str = "con",
    freq: str = "annual",
) -> JSONDict | Response:
    """Time series for one account code, e.g. 3.05 (operating result/EBIT)."""
    if (cached := _cache_headers(request, response)) is not None:
        return cached
    with session() as s:
        stmt = (
            select(Fact)
            .where(
                Fact.cd_cvm == cd_cvm,
                Fact.scope == scope,
                Fact.account_code == code,
                _period_clause(freq),
            )
            .order_by(Fact.period.desc())
        )
        rows = list(s.execute(stmt).scalars())
        values: dict[str, float | None] = {f.period: f.value for f in rows}
        growth = _growth(
            {p: {"value": v} for p, v in values.items()},
            include_qoq=(freq == "quarterly"),
        )
        return {
            "cd_cvm": cd_cvm,
            "account_code": code,
            "account_desc": rows[0].account_desc if rows else None,
            "freq": freq,
            "series": [
                {
                    "period": f.period,
                    "value": f.value,
                    "qoq": growth[f.period]["value"]["qoq"],
                    "yoy": growth[f.period]["value"]["yoy"],
                }
                for f in rows
            ],
        }


@app.get("/companies/{cd_cvm}/indicators", response_model=None)
def company_indicators(
    cd_cvm: int,
    request: Request,
    response: Response,
    scope: str = "con",
    freq: str = "annual",
    year: int | None = None,
    price: float | None = None,
) -> JSONDict | Response:
    if price is None and (cached := _cache_headers(request, response)) is not None:
        return cached
    months = _months_for(freq)
    with session() as s:
        stmt = select(Indicator).where(
            Indicator.cd_cvm == cd_cvm,
            Indicator.scope == scope,
            Indicator.period_months == months,
        )
        if year:
            stmt = stmt.where(Indicator.fiscal_year == year)
        stmt = stmt.order_by(Indicator.period.desc(), Indicator.name)
        rows = list(s.execute(stmt).scalars())

        by_period: dict[str, dict[str, float | None]] = {}
        for r in rows:
            by_period.setdefault(r.period, {})[r.name] = r.value

        growth = _growth(by_period, include_qoq=(freq == "quarterly"))

        # Optionally layer live price-based ratios onto the latest period.
        if price is not None and by_period:
            latest = max(by_period)
            facts = list(
                s.execute(
                    select(Fact).where(
                        Fact.cd_cvm == cd_cvm,
                        Fact.scope == scope,
                        Fact.period == latest,
                        Fact.period_months.in_([months, 0]),
                    )
                ).scalars()
            )
            sh = s.execute(
                select(Shares.total).where(
                    Shares.cd_cvm == cd_cvm, Shares.period == latest
                )
            ).scalar()
            li = indicators.line_items(
                FactRow(f.statement, f.account_code, f.account_desc, f.value)
                for f in facts
            )
            deriv = indicators.derived(li)
            by_period[latest].update(indicators.price_based(li, deriv, price, sh))

        return {
            "cd_cvm": cd_cvm,
            "scope": scope,
            "freq": freq,
            "periods": by_period,
            "growth": growth,
        }


@app.get("/companies/{cd_cvm}/documents", response_model=None)
def company_documents(
    cd_cvm: int,
    request: Request,
    response: Response,
    limit: Annotated[int, Query(le=500)] = 50,
) -> JSONList | Response:
    if (cached := _cache_headers(request, response)) is not None:
        return cached
    with session() as s:
        stmt = (
            select(Document)
            .where(Document.cd_cvm == cd_cvm)
            .order_by(Document.deliver_date.desc())
            .limit(limit)
        )
        return [
            {
                "category": d.category,
                "type": d.doc_type,
                "subject": d.subject,
                "ref_date": d.ref_date,
                "deliver_date": d.deliver_date,
                "url": d.url,
            }
            for d in s.execute(stmt).scalars()
        ]


@app.get("/screen", response_model=None)
def screen(
    request: Request,
    response: Response,
    scope: str = "con",
    freq: str = "annual",
    fields: str | None = None,
    limit: Annotated[int, Query(le=2000)] = 500,
) -> JSONList | Response:
    """Latest indicators per ticker, joined to companies, for batch screening.

    `fields` is a comma-separated whitelist; default returns the common headline set.
    Price-based ratios (P/E, P/B, EV/EBITDA, ...) are not included — callers join
    them in client-side using a live price source.
    """
    if (cached := _cache_headers(request, response)) is not None:
        return cached
    wanted = (
        {n.strip() for n in fields.split(",") if n.strip()}
        if fields
        else {
            "revenue", "ebit", "ebitda", "net_income", "equity", "net_debt",
            "gross_margin", "operating_margin", "net_margin", "ebitda_margin",
            "roe", "roa", "roic", "debt_to_equity", "current_ratio",
        }
    )
    months = _months_for(freq)

    def load() -> JSONList:
        with session() as s:
            latest_period = (
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
                .join(latest_period, latest_period.c.cd_cvm == Company.cd_cvm)
                .join(
                    Indicator,
                    and_(
                        Indicator.cd_cvm == Company.cd_cvm,
                        Indicator.period == latest_period.c.period,
                        Indicator.scope == scope,
                        Indicator.period_months == months,
                    ),
                )
                .where(Indicator.name.in_(wanted))
                .order_by(Ticker.ticker)
            ).all()
            by_ticker: dict[str, dict[str, object]] = {}
            typed_rows = cast(
                list[tuple[str, str | None, int, str, str | None, str, str, float | None]],
                rows,
            )
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
            out = list(by_ticker.values())
            return out[:limit]

    return cache.get_or_set(f"screen:{scope}:{freq}:{fields}:{limit}", load)


@app.get("/tickers/{ticker}", response_model=None)
def by_ticker(
    ticker: str, request: Request, response: Response
) -> JSONDict | Response:
    if (cached := _cache_headers(request, response)) is not None:
        return cached
    with session() as s:
        t = s.execute(
            select(Ticker).where(Ticker.ticker == ticker.upper())
        ).scalar()
        if t is None:
            response.status_code = 404
            return {"error": "not found"}
        c = s.get(Company, t.cd_cvm)
        return {
            "ticker": t.ticker,
            "kind": t.kind,
            "cd_cvm": t.cd_cvm,
            "name": c.name if c else None,
        }
