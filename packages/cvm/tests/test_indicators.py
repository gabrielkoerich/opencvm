"""Unit tests for the pure indicator math.

No DB, no network — exercises line_items / derived / per_share / price_based
against synthetic FactRow data so changes to the formulas can't silently break
real fundamentals output.
"""

from __future__ import annotations

from math import isclose

import pytest

from cvm.indicators import (
    FactRow,
    compute_all,
    derived,
    line_items,
    per_share,
    price_based,
)


def _f(stmt: str, code: str, desc: str, value: float) -> FactRow:
    return FactRow(statement=stmt, account_code=code, account_desc=desc, value=value)


# Petrobras-ish 2024 consolidated numbers (BRL), rounded so the math is checkable
# by hand. Don't change these without updating the expected ratios below.
_FACTS: list[FactRow] = [
    _f("DRE", "3.01", "Receita", 500_000),
    _f("DRE", "3.02", "CMV", -250_000),
    _f("DRE", "3.03", "Lucro Bruto", 250_000),
    _f("DRE", "3.04", "Despesas Op", -100_000),
    _f("DRE", "3.05", "EBIT", 150_000),
    _f("DRE", "3.06", "Resultado Financeiro", -20_000),
    _f("DRE", "3.07", "LAIR", 130_000),
    _f("DRE", "3.08", "Tributos", -40_000),
    _f("DRE", "3.11", "Lucro Líquido", 90_000),
    _f("BPA", "1", "Ativo Total", 1_000_000),
    _f("BPA", "1.01", "Ativo Circulante", 200_000),
    _f("BPA", "1.01.01", "Caixa", 30_000),
    _f("BPA", "1.01.02", "Aplicações", 20_000),
    _f("BPA", "1.02", "Ativo Não Circ.", 800_000),
    _f("BPP", "2.01", "Passivo Circ.", 150_000),
    _f("BPP", "2.01.04", "Empréstimos CP", 50_000),
    _f("BPP", "2.02", "Passivo Não Circ.", 350_000),
    _f("BPP", "2.02.01", "Empréstimos LP", 250_000),
    _f("BPP", "2.03", "Patrimônio Líquido", 500_000),
    _f("DFC_MI", "6.01", "Caixa Operacional", 200_000),
    _f("DFC_MI", "6.02", "Caixa Investimento", -120_000),
    _f("DFC_MI", "6.03", "Caixa Financiamento", -60_000),
    # D&A appears as a sub-account in the cash flow reconciliation
    _f("DFC_MI", "6.01.01.02", "Depreciação e Amortização", 50_000),
]


def test_line_items_pulls_named_codes() -> None:
    li = line_items(_FACTS)
    assert li["revenue"] == 500_000
    assert li["net_income"] == 90_000
    assert li["equity"] == 500_000
    assert li["operating_cash_flow"] == 200_000
    # D&A is scanned by description from the cash flow statement, value is abs()
    assert li["depreciation_amortization"] == 50_000


def test_line_items_falls_back_from_mi_to_md() -> None:
    """Direct-method (DFC_MD) substitutes when indirect (DFC_MI) is absent."""
    facts = [_f("DFC_MD", "6.01", "Caixa Operacional", 111_000)]
    li = line_items(facts)
    assert li["operating_cash_flow"] == 111_000


def test_derived_margins_and_ratios() -> None:
    li = line_items(_FACTS)
    d = derived(li)

    # ebitda = ebit + D&A
    assert d["ebitda"] == 200_000
    # net debt = (50k + 250k) - (30k + 20k)
    assert d["net_debt"] == 250_000
    # margins
    assert d["gross_margin"] == pytest.approx(0.5)
    assert d["operating_margin"] == pytest.approx(0.3)
    assert d["net_margin"] == pytest.approx(0.18)
    assert d["ebitda_margin"] == pytest.approx(0.4)
    # returns
    assert d["roe"] == pytest.approx(0.18)
    assert d["roa"] == pytest.approx(0.09)
    # leverage
    assert d["debt_to_equity"] == pytest.approx(0.6)
    assert d["equity_ratio"] == pytest.approx(0.5)
    # liquidity
    assert d["current_ratio"] == pytest.approx(200_000 / 150_000)
    assert d["cash_ratio"] == pytest.approx(50_000 / 150_000)
    # efficiency
    assert d["asset_turnover"] == pytest.approx(0.5)


def test_derived_nopat_and_roic_use_effective_tax_rate() -> None:
    """ROIC drops out cleanly: nopat / invested_capital."""
    li = line_items(_FACTS)
    d = derived(li)

    # eff tax rate = -taxes / pretax = 40k / 130k
    assert d["effective_tax_rate"] == pytest.approx(40_000 / 130_000)
    # nopat = ebit * (1 - eff_tax)
    expected_nopat = 150_000 * (1 - 40_000 / 130_000)
    assert d["nopat"] == pytest.approx(expected_nopat)
    # invested capital = equity + gross debt = 500k + 300k
    assert d["invested_capital"] == 800_000
    assert d["roic"] == pytest.approx(expected_nopat / 800_000)


def test_derived_returns_none_when_inputs_missing() -> None:
    li = {"revenue": 100.0}  # nothing else
    d = derived(li)
    assert d["gross_margin"] is None
    assert d["roe"] is None
    assert d["debt_to_equity"] is None
    # gross_debt with no inputs collapses to 0, so net_debt is None per the code
    assert d["net_debt"] is None


def test_per_share_handles_missing_shares() -> None:
    li = line_items(_FACTS)
    assert per_share(li, None) == {"eps": None, "book_value_per_share": None}
    assert per_share(li, 0) == {"eps": None, "book_value_per_share": None}

    ps = per_share(li, 10_000)
    assert ps["eps"] == pytest.approx(9.0)
    assert ps["book_value_per_share"] == pytest.approx(50.0)


def test_price_based_assembles_market_cap_and_ev_bridge() -> None:
    li = line_items(_FACTS)
    d = derived(li)

    pb = price_based(li, d, price=40.0, shares=10_000)
    assert pb["market_cap"] == 400_000
    # EV = market cap + net debt (250k from above)
    assert pb["enterprise_value"] == 650_000
    assert pb["pe"] == pytest.approx(400_000 / 90_000)
    assert pb["pb"] == pytest.approx(400_000 / 500_000)
    assert pb["ps"] == pytest.approx(400_000 / 500_000)
    assert pb["ev_ebitda"] == pytest.approx(650_000 / 200_000)
    assert pb["ev_ebit"] == pytest.approx(650_000 / 150_000)
    assert pb["earnings_yield"] == pytest.approx(90_000 / 400_000)


def test_price_based_empty_without_price_or_shares() -> None:
    li = line_items(_FACTS)
    d = derived(li)
    assert price_based(li, d, price=None, shares=10_000) == {}
    assert price_based(li, d, price=40.0, shares=None) == {}
    assert price_based(li, d, price=40.0, shares=0) == {}


def test_compute_all_includes_line_items_derived_and_per_share() -> None:
    out = compute_all(_FACTS, shares=10_000)
    revenue = out["revenue"]
    assert revenue is not None and isclose(revenue, 500_000.0)
    assert out["ebitda"] == 200_000
    assert out["eps"] == pytest.approx(9.0)
