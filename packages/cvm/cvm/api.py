"""FastAPI read API over the CVM store.

Responses carry a sync-version ``ETag`` + ``Cache-Control`` so clients (and the
Laravel frontend) can cache aggressively; CVM data only changes when a sync runs.
Price-based ratios are computed on demand from an injected ``price`` query param,
since prices come from a live source (brapi), not CVM.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query, Request, Response
from sqlalchemy import func, select

from . import cache, indicators
from .db import Company, Document, Fact, Indicator, Shares, Ticker, session
from .indicators import FactRow

app = FastAPI(title="CVM Fundamentals API", version="0.1.0")

JSONDict = dict[str, object]
JSONList = list[dict[str, object]]


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
    year: int | None = None,
) -> JSONList | Response:
    if (cached := _cache_headers(request, response)) is not None:
        return cached
    with session() as s:
        stmt = select(Fact).where(
            Fact.cd_cvm == cd_cvm,
            Fact.statement == statement,
            Fact.scope == scope,
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
            )
            .order_by(Fact.period.desc())
        )
        rows = list(s.execute(stmt).scalars())
        return {
            "cd_cvm": cd_cvm,
            "account_code": code,
            "account_desc": rows[0].account_desc if rows else None,
            "series": [{"period": f.period, "value": f.value} for f in rows],
        }


@app.get("/companies/{cd_cvm}/indicators", response_model=None)
def company_indicators(
    cd_cvm: int,
    request: Request,
    response: Response,
    scope: str = "con",
    year: int | None = None,
    price: float | None = None,
) -> JSONDict | Response:
    if price is None and (cached := _cache_headers(request, response)) is not None:
        return cached
    with session() as s:
        stmt = select(Indicator).where(
            Indicator.cd_cvm == cd_cvm, Indicator.scope == scope
        )
        if year:
            stmt = stmt.where(Indicator.fiscal_year == year)
        stmt = stmt.order_by(Indicator.period.desc(), Indicator.name)
        rows = list(s.execute(stmt).scalars())

        by_period: dict[str, dict[str, float | None]] = {}
        for r in rows:
            by_period.setdefault(r.period, {})[r.name] = r.value

        # Optionally layer live price-based ratios onto the latest period.
        if price is not None and by_period:
            latest = max(by_period)
            facts = list(
                s.execute(
                    select(Fact).where(
                        Fact.cd_cvm == cd_cvm,
                        Fact.scope == scope,
                        Fact.period == latest,
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

        return {"cd_cvm": cd_cvm, "scope": scope, "periods": by_period}


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
