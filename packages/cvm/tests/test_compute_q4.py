"""Test the standalone-Q4 derivation: CVM ships no Q4 ITR, so we back it out as
annual (DFP) minus (Q1 + Q2 + Q3). Anything missing a quarter is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

from cvm.compute import _derive_q4_rows


@dataclass
class _F:
    """Minimal shape the derivation reads from a Fact row."""

    scope: str
    fiscal_year: int
    statement: str
    account_code: str
    account_desc: str
    period: str
    period_months: int
    value: float


def _annual(code: str, desc: str, value: float, year: int = 2024) -> _F:
    return _F("con", year, "DRE", code, desc, f"{year}-12-31", 12, value)


def _q(code: str, desc: str, value: float, end_md: str, year: int = 2024) -> _F:
    return _F("con", year, "DRE", code, desc, f"{year}-{end_md}", 3, value)


def test_q4_is_annual_minus_first_three_quarters() -> None:
    facts = [
        _annual("3.01", "Receita", 1000.0),
        _q("3.01", "Receita", 200.0, "03-31"),
        _q("3.01", "Receita", 250.0, "06-30"),
        _q("3.01", "Receita", 300.0, "09-30"),
    ]
    rows = _derive_q4_rows(9999, facts)  # pyright: ignore[reportArgumentType]
    assert len(rows) == 1
    r = rows[0]
    assert r["period"] == "2024-12-31"
    assert r["period_months"] == 3
    assert r["dataset"] == "derived"
    assert r["statement"] == "DRE"
    assert r["account_code"] == "3.01"
    assert r["value"] == 1000.0 - (200.0 + 250.0 + 300.0)
    assert r["cd_cvm"] == 9999
    assert r["fiscal_year"] == 2024


def test_missing_quarter_skips_derivation() -> None:
    """Without all of Q1/Q2/Q3 we can't back out a clean Q4."""
    facts = [
        _annual("3.01", "Receita", 1000.0),
        _q("3.01", "Receita", 200.0, "03-31"),
        _q("3.01", "Receita", 250.0, "06-30"),
        # Q3 missing
    ]
    assert _derive_q4_rows(9999, facts) == []  # pyright: ignore[reportArgumentType]


def test_consolidated_and_individual_scopes_are_independent() -> None:
    """A consolidated annual shouldn't borrow individual quarters and vice versa."""
    facts = [
        _F("con", 2024, "DRE", "3.01", "Receita", "2024-12-31", 12, 1000.0),
        _F("con", 2024, "DRE", "3.01", "Receita", "2024-03-31", 3, 200.0),
        _F("con", 2024, "DRE", "3.01", "Receita", "2024-06-30", 3, 250.0),
        _F("con", 2024, "DRE", "3.01", "Receita", "2024-09-30", 3, 300.0),
        # individual only has annual — no quarters → must be skipped
        _F("ind", 2024, "DRE", "3.01", "Receita", "2024-12-31", 12, 900.0),
    ]
    rows = _derive_q4_rows(9999, facts)  # pyright: ignore[reportArgumentType]
    scopes = {r["scope"] for r in rows}
    assert scopes == {"con"}
    assert rows[0]["value"] == 250.0


def test_only_year_end_annual_counts() -> None:
    """A row with period_months=12 but period not ending 12-31 is not 'annual'."""
    facts = [
        _F("con", 2024, "DRE", "3.01", "Receita", "2024-06-30", 12, 1000.0),  # ttm-ish
        _q("3.01", "Receita", 200.0, "03-31"),
        _q("3.01", "Receita", 250.0, "06-30"),
        _q("3.01", "Receita", 300.0, "09-30"),
    ]
    assert _derive_q4_rows(9999, facts) == []  # pyright: ignore[reportArgumentType]
