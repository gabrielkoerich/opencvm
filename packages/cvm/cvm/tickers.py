"""Build a fresh CD_CVM <-> ticker map.

The old project shipped a 2011-era ``stocks.json``; instead we pull the *current*
B3 listed-companies API, which exposes ``codeCVM`` plus each company's trading
codes (PETR3, PETR4, ...). ``stocks.json`` is only used as an offline seed when
B3 is unreachable, and its stale prices are dropped.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import requests
from sqlalchemy import select

from .db import Company, Ticker, session

_B3 = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"
_HEADERS = {"User-Agent": "Mozilla/5.0 (bean-cvm)"}
_TIMEOUT = 30
_DETAIL_WORKERS = 16


def _encode(params: Mapping[str, object]) -> str:
    return base64.b64encode(json.dumps(params).encode()).decode()


def _kind_from_ticker(ticker: str) -> str | None:
    digits = "".join(c for c in ticker if c.isdigit())
    return {
        "3": "ON",
        "4": "PN",
        "5": "PNA",
        "6": "PNB",
        "11": "UNT",
        "34": "BDR",
        "31": "BDR",
        "32": "BDR",
        "33": "BDR",
        "35": "BDR",
    }.get(digits)


def fetch_b3_companies() -> list[dict[str, str]]:
    """Paginated list of listed companies with codeCVM + issuing root."""
    out: list[dict[str, str]] = []
    page = 1
    while True:
        params = {"language": "pt-br", "pageNumber": page, "pageSize": 120}
        url = f"{_B3}/GetInitialCompanies/{_encode(params)}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
        except (requests.RequestException, ValueError):
            break
        results = cast("list[dict[str, object]]", data.get("results") or [])
        for r in results:
            cd = str(r.get("codeCVM") or "").strip()
            if cd.isdigit():
                out.append(
                    {
                        "cd_cvm": cd,
                        "issuing": str(r.get("issuingCompany") or ""),
                        "name": str(r.get("companyName") or ""),
                    }
                )
        page_info = cast("dict[str, object]", data.get("page") or {})
        total_pages = int(str(page_info.get("totalPages") or 0))
        if page >= total_pages or not results:
            break
        page += 1
    return out


def fetch_b3_codes(cd_cvm: str) -> list[str]:
    """Trading codes (tickers) for one company via GetDetail.otherCodes."""
    params = {"codeCVM": cd_cvm, "language": "pt-br"}
    url = f"{_B3}/GetDetail/{_encode(params)}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data: dict[str, object] = resp.json()  # pyright: ignore[reportAny]
    except (requests.RequestException, ValueError):
        return []
    other = cast("list[dict[str, object]]", data.get("otherCodes") or [])
    return [str(c.get("code")).strip() for c in other if c.get("code")]


def _store(rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    with session() as s:
        stmt = sqlite_insert(Ticker).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={
                "cd_cvm": stmt.excluded.cd_cvm,
                "kind": stmt.excluded.kind,
                "source": stmt.excluded.source,
            },
        )
        s.execute(stmt)
    return len(rows)


def _known_cd_cvm() -> set[int]:
    """cd_cvm already ingested into companies; tickers FK requires it."""
    with session() as s:
        return {cd for (cd,) in s.execute(select(Company.cd_cvm)).all()}


def refresh_from_b3() -> int:
    companies = fetch_b3_companies()
    known = _known_cd_cvm()
    targets = [c for c in companies if int(c["cd_cvm"]) in known] if known else companies

    def codes_for(c: dict[str, str]) -> tuple[int, list[str]]:
        return int(c["cd_cvm"]), fetch_b3_codes(c["cd_cvm"])

    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=_DETAIL_WORKERS) as ex:
        for cd, codes in ex.map(codes_for, targets):
            for code in codes:
                rows.append(
                    {
                        "cd_cvm": cd,
                        "ticker": code,
                        "kind": _kind_from_ticker(code),
                        "source": "b3",
                    }
                )
    return _store(rows)


def seed_from_stocks_json(path: str | Path) -> int:
    """Offline fallback: ccvm -> code map from the legacy stocks.json (no prices)."""
    p = Path(path)
    if not p.exists():
        return 0
    parsed: object = json.loads(p.read_text())  # pyright: ignore[reportAny]
    entries_obj: object
    if isinstance(parsed, dict):
        values = list(cast("dict[str, object]", parsed).values())
        entries_obj = values[0] if values else []
    else:
        entries_obj = parsed
    entries = cast("list[dict[str, object]]", entries_obj)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for e in entries:
        code = str(e.get("code") or "").strip()
        ccvm = e.get("ccvm")
        if not code or ccvm is None or code in seen:
            continue
        seen.add(code)
        rows.append(
            {
                "cd_cvm": int(str(ccvm)),
                "ticker": code,
                "kind": e.get("type") or _kind_from_ticker(code),
                "source": "stocks.json",
            }
        )
    return _store(rows)


def refresh_tickers(stocks_json: str | Path | None = None) -> int:
    """Refresh from B3; fall back to the legacy seed only if B3 yields nothing."""
    n = refresh_from_b3()
    if n == 0 and stocks_json is not None:
        n = seed_from_stocks_json(stocks_json)
    return n
