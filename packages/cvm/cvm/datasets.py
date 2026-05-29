"""Registry of CVM open-data datasets.

The public portal (dados.cvm.gov.br) ships bulk yearly ZIPs, one per dataset per
year, plus a couple of single-file registries. Each financial-statement ZIP
(DFP/ITR) contains one CSV per statement type and scope, e.g.
``dfp_cia_aberta_DRE_con_2024.csv``.

This module only describes *where* data lives and *which* shards to fetch; the
downloading lives in ``download.py`` and parsing in ``ingest.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"

# Statement types we ingest into the long-format facts table. Codes are the CVM
# CD_CONTA roots: 1=Ativo, 2=Passivo, 3=DRE, 6=DFC, 7=DVA.
STATEMENTS: tuple[str, ...] = ("BPA", "BPP", "DRE", "DFC_MD", "DFC_MI", "DVA")
SCOPES: tuple[str, ...] = ("con", "ind")  # consolidated vs individual


@dataclass(frozen=True)
class Dataset:
    """A CVM dataset shardable by year."""

    key: str
    """Short identifier, e.g. ``dfp``."""
    url_template: str
    """``str.format``-able URL with a ``{year}`` placeholder (or none for single files)."""
    first_year: int
    """Earliest year available on the portal; full backfill starts here."""
    prefix: str = ""
    """CSV filename prefix inside the ZIP, e.g. ``dfp_cia_aberta``."""
    yearly: bool = True
    """False for single-file registries (CAD)."""

    def url(self, year: int | None = None) -> str:
        if not self.yearly:
            return self.url_template
        assert year is not None
        return self.url_template.format(year=year)

    def years(self, through: int | None = None) -> list[int]:
        last = through or date.today().year
        return list(range(self.first_year, last + 1))

    def statement_csv(self, statement: str, scope: str, year: int) -> str:
        """CSV filename for a statement/scope inside a yearly financial ZIP."""
        return f"{self.prefix}_{statement}_{scope}_{year}.csv"

    def member_csv(self, suffix: str, year: int) -> str:
        """CSV filename for a non-statement member, e.g. composicao_capital."""
        return f"{self.prefix}_{suffix}_{year}.csv"


DATASETS: dict[str, Dataset] = {
    "dfp": Dataset(
        key="dfp",
        url_template=f"{_BASE}/DOC/DFP/DADOS/dfp_cia_aberta_{{year}}.zip",
        first_year=2010,
        prefix="dfp_cia_aberta",
    ),
    "itr": Dataset(
        key="itr",
        url_template=f"{_BASE}/DOC/ITR/DADOS/itr_cia_aberta_{{year}}.zip",
        first_year=2011,
        prefix="itr_cia_aberta",
    ),
    "ipe": Dataset(
        key="ipe",
        url_template=f"{_BASE}/DOC/IPE/DADOS/ipe_cia_aberta_{{year}}.zip",
        first_year=2003,
        prefix="ipe_cia_aberta",
    ),
    "cad": Dataset(
        key="cad",
        url_template=f"{_BASE}/CAD/DADOS/cad_cia_aberta.csv",
        first_year=0,
        yearly=False,
    ),
}

# Datasets whose CSVs feed the long-format facts table.
FINANCIAL_DATASETS: tuple[str, ...] = ("dfp", "itr")


def financial_shards(through: int | None = None) -> list[tuple[str, int, str, str]]:
    """All (dataset, year, statement, scope) tuples for a full financial backfill."""
    shards: list[tuple[str, int, str, str]] = []
    for key in FINANCIAL_DATASETS:
        ds = DATASETS[key]
        for year in ds.years(through):
            for statement in STATEMENTS:
                for scope in SCOPES:
                    shards.append((key, year, statement, scope))
    return shards
