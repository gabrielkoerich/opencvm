"""Fundamental indicators computed from the normalized facts.

Two layers:
  * fundamental indicators (margins, returns, leverage, per-share) depend only on
    CVM data and are precomputed + stored in the ``indicators`` table;
  * price-based ratios (P/E, P/B, EV/EBITDA, ...) need a *live* price and are
    computed on the fly by ``price_based`` with price + share count injected.

Account codes follow the CVM standard chart (non-financial companies):
1=Ativo, 2=Passivo/PL, 3=DRE, 6=DFC. Banks/insurers use a different chart, so a
few items will be absent for them — callers should treat ``None`` as "n/a".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# logical name -> (statement, exact account code)
LINE_ITEM_CODES: dict[str, tuple[str, str]] = {
    "revenue": ("DRE", "3.01"),
    "cogs": ("DRE", "3.02"),
    "gross_profit": ("DRE", "3.03"),
    "operating_expenses": ("DRE", "3.04"),
    "ebit": ("DRE", "3.05"),  # Resultado antes do financeiro e tributos
    "financial_result": ("DRE", "3.06"),
    "pretax_income": ("DRE", "3.07"),
    "taxes": ("DRE", "3.08"),
    "net_income": ("DRE", "3.11"),
    "total_assets": ("BPA", "1"),
    "current_assets": ("BPA", "1.01"),
    "cash": ("BPA", "1.01.01"),
    "short_term_investments": ("BPA", "1.01.02"),
    "noncurrent_assets": ("BPA", "1.02"),
    "current_liabilities": ("BPP", "2.01"),
    "current_debt": ("BPP", "2.01.04"),
    "noncurrent_liabilities": ("BPP", "2.02"),
    "noncurrent_debt": ("BPP", "2.02.01"),
    "equity": ("BPP", "2.03"),
    "operating_cash_flow": ("DFC_MI", "6.01"),
    "investing_cash_flow": ("DFC_MI", "6.02"),
    "financing_cash_flow": ("DFC_MI", "6.03"),
}


@dataclass
class FactRow:
    statement: str
    account_code: str
    account_desc: str
    value: float


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _find_da(facts: Iterable[FactRow]) -> float | None:
    """Depreciation & amortization, scanned from the cash-flow statement."""
    total = 0.0
    found = False
    for f in facts:
        if not f.statement.startswith("DFC"):
            continue
        desc = f.account_desc.lower()
        if "deprecia" in desc or "amortiza" in desc or "exaust" in desc:
            total += abs(f.value)
            found = True
    return total if found else None


def line_items(facts: Iterable[FactRow]) -> dict[str, float]:
    """Pull the named line items from a company's facts for one period/scope."""
    facts = list(facts)
    by_key: dict[tuple[str, str], float] = {}
    for f in facts:
        by_key[(f.statement, f.account_code)] = f.value

    out: dict[str, float] = {}
    for name, (stmt, code) in LINE_ITEM_CODES.items():
        v = by_key.get((stmt, code))
        if v is None and stmt == "DFC_MI":
            v = by_key.get(("DFC_MD", code))  # fall back to direct-method cash flow
        if v is not None:
            out[name] = v

    da = _find_da(facts)
    if da is not None:
        out["depreciation_amortization"] = da
    return out


def derived(li: dict[str, float]) -> dict[str, float | None]:
    """Compute stored fundamental indicators from raw line items."""
    g = li.get

    cash = (g("cash") or 0.0) + (g("short_term_investments") or 0.0)
    gross_debt = (g("current_debt") or 0.0) + (g("noncurrent_debt") or 0.0)
    net_debt = gross_debt - cash if gross_debt else None

    ebit = g("ebit")
    da = g("depreciation_amortization")
    ebitda = ebit + da if (ebit is not None and da is not None) else None

    pretax = g("pretax_income")
    taxes = g("taxes")
    eff_tax = _safe_div(-(taxes or 0.0), pretax) if pretax else None
    nopat = ebit * (1 - eff_tax) if (ebit is not None and eff_tax is not None) else None

    equity = g("equity")
    invested_capital = (equity + gross_debt) if equity is not None else None

    out: dict[str, float | None] = {
        # absolute (derived) items
        "cash_and_equivalents": cash,
        "gross_debt": gross_debt,
        "net_debt": net_debt,
        "ebitda": ebitda,
        "nopat": nopat,
        "invested_capital": invested_capital,
        "effective_tax_rate": eff_tax,
        # margins
        "gross_margin": _safe_div(g("gross_profit"), g("revenue")),
        "operating_margin": _safe_div(ebit, g("revenue")),
        "net_margin": _safe_div(g("net_income"), g("revenue")),
        "ebitda_margin": _safe_div(ebitda, g("revenue")),
        # returns
        "roe": _safe_div(g("net_income"), equity),
        "roa": _safe_div(g("net_income"), g("total_assets")),
        "roic": _safe_div(nopat, invested_capital),
        # liquidity
        "current_ratio": _safe_div(g("current_assets"), g("current_liabilities")),
        "cash_ratio": _safe_div(cash, g("current_liabilities")),
        # leverage
        "debt_to_equity": _safe_div(gross_debt, equity),
        "net_debt_to_ebitda": _safe_div(net_debt, ebitda),
        "equity_ratio": _safe_div(equity, g("total_assets")),
        # efficiency
        "asset_turnover": _safe_div(g("revenue"), g("total_assets")),
    }
    return out


def per_share(li: dict[str, float], shares: float | None) -> dict[str, float | None]:
    if not shares:
        return {"eps": None, "book_value_per_share": None}
    return {
        "eps": _safe_div(li.get("net_income"), shares),
        "book_value_per_share": _safe_div(li.get("equity"), shares),
    }


def price_based(
    li: dict[str, float],
    deriv: dict[str, float | None],
    price: float | None,
    shares: float | None,
) -> dict[str, float | None]:
    """Live-computed valuation ratios. Returns {} when price/shares missing."""
    if not price or not shares:
        return {}
    market_cap = price * shares
    net_income = li.get("net_income")
    equity = li.get("equity")
    revenue = li.get("revenue")
    ebitda = deriv.get("ebitda")
    ebit = li.get("ebit")
    net_debt = deriv.get("net_debt") or 0.0
    ev = market_cap + net_debt
    return {
        "market_cap": market_cap,
        "enterprise_value": ev,
        "pe": _safe_div(market_cap, net_income),
        "pb": _safe_div(market_cap, equity),
        "ps": _safe_div(market_cap, revenue),
        "ev_ebitda": _safe_div(ev, ebitda),
        "ev_ebit": _safe_div(ev, ebit),
        "earnings_yield": _safe_div(net_income, market_cap),
    }


def compute_all(
    facts: Iterable[FactRow],
    shares: float | None = None,
) -> dict[str, float | None]:
    """All fundamental indicators (no price). Line items + derived + per-share."""
    li = line_items(facts)
    out: dict[str, float | None] = {k: float(v) for k, v in li.items()}
    out.update(derived(li))
    out.update(per_share(li, shares))
    return out
