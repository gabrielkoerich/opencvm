"""Parse CVM CSVs into the normalized SQLite store.

Normalization rules (the part the old PHP project found painful):
  * ``ORDEM_EXERC`` — keep only ``ÚLTIMO`` (current period; drop the prior-year
    comparative column that CVM bundles into the same file).
  * ``VERSAO`` — companies refile; keep the highest version per (company, period).
  * ``ESCALA_MOEDA`` — scale ``VL_CONTA`` to absolute BRL (MIL ×1000, MILHÃO ×1e6).
  * scope ``con`` (consolidated) vs ``ind`` (individual) comes from the filename.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import download
from .datasets import DATASETS, FLOW_STATEMENTS, SCOPES, STATEMENTS
from .db import Company, Document, Fact, Shares, get_engine, session

_ENCODING = "latin-1"
_SCALE = {"MIL": 1000.0, "MILHAO": 1_000_000.0, "MILHÃO": 1_000_000.0, "UNIDADE": 1.0}


def _read_csv(path: str, usecols: list[str] | None = None) -> pd.DataFrame:
    return pd.read_csv(
        path,
        sep=";",
        encoding=_ENCODING,
        dtype=str,
        usecols=usecols,
        on_bad_lines="skip",
    )


def _digits(cnpj: str | None) -> str:
    return re.sub(r"\D", "", cnpj or "")


def _records(df: pd.DataFrame) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", df.to_dict(orient="records"))


def _scale(escala: pd.Series) -> pd.Series:
    return escala.str.upper().map(_SCALE).fillna(1.0)


def _period_months(ini: pd.Series, fim: pd.Series) -> pd.Series:
    """Inclusive month span between DT_INI_EXERC and DT_FIM_EXERC (3/6/9/12)."""
    di = pd.to_datetime(ini, errors="coerce")
    df = pd.to_datetime(fim, errors="coerce")
    return (df.dt.year - di.dt.year) * 12 + (df.dt.month - di.dt.month) + 1


def _keep_latest(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Drop comparative columns and refiled older versions."""
    if "ORDEM_EXERC" in df.columns:
        df = df[df["ORDEM_EXERC"].str.upper().str.startswith("ÚLT", na=False)]
    df = df.copy()
    df["VERSAO"] = pd.to_numeric(df["VERSAO"], errors="coerce").fillna(0).astype(int)
    latest = df.groupby(keys)["VERSAO"].transform("max")
    return df[df["VERSAO"] == latest]


def _upsert(
    session_: Session,
    model: type,
    rows: list[dict[str, object]],
    index_elements: list[str],
    update_cols: list[str],
    chunk: int = 5000,
) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        stmt = sqlite_insert(model).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_={c: getattr(stmt.excluded, c) for c in update_cols},
        )
        session_.execute(stmt)
        total += len(batch)
    return total


def _upsert_companies(session_: Session, df: pd.DataFrame) -> None:
    sub = df[["CD_CVM", "DENOM_CIA", "CNPJ_CIA"]].drop_duplicates(subset=["CD_CVM"])
    rows: list[dict[str, object]] = []
    for d in _records(sub):
        rows.append(
            {
                "cd_cvm": int(str(d["CD_CVM"])),
                "name": d["DENOM_CIA"],
                "cnpj": d["CNPJ_CIA"],
            }
        )
    _upsert(session_, Company, rows, ["cd_cvm"], ["name", "cnpj"])


def ingest_dataset_year(dataset_key: str, year: int) -> dict[str, int]:
    """Download one dataset-year ZIP, parse every member, then delete the ZIP.

    Download → parse → delete: the ZIP and each extracted CSV are removed as soon
    as they are consumed, so a full backfill never accumulates on disk.
    """
    counts = {"facts": 0, "shares": 0}
    with download.temp_dataset(dataset_key, year) as zip_path:
        for statement in STATEMENTS:
            for scope in SCOPES:
                counts["facts"] += _ingest_statement(
                    zip_path, dataset_key, statement, scope, year
                )
        counts["shares"] += _ingest_shares(zip_path, dataset_key, year)
    return counts


def _ingest_statement(
    zip_path: Path, dataset_key: str, statement: str, scope: str, year: int
) -> int:
    """Parse + upsert one statement/scope CSV from an already-downloaded ZIP."""
    ds = DATASETS[dataset_key]
    member = ds.statement_csv(statement, scope, year)
    csv_path = download.extract_member(zip_path, member)
    if csv_path is None:
        return 0
    try:
        return _store_statement(csv_path, dataset_key, statement, scope)
    finally:
        csv_path.unlink(missing_ok=True)


def _store_statement(
    csv_path: Path, dataset_key: str, statement: str, scope: str
) -> int:
    df = _read_csv(str(csv_path))
    if df.empty or "CD_CONTA" not in df.columns:
        return 0

    df = df.dropna(subset=["CD_CVM", "DT_FIM_EXERC", "CD_CONTA", "VL_CONTA"])
    df = df[df["CD_CVM"].str.strip() != ""].copy()

    # Flow statements report both year-to-date (3/6/9/12) and quarter-alone (3)
    # spans for the same period-end. Keep only standalone quarters and full years;
    # balance sheets are point-in-time snapshots (months = 0).
    if statement in FLOW_STATEMENTS and "DT_INI_EXERC" in df.columns:
        df["_months"] = _period_months(df["DT_INI_EXERC"], df["DT_FIM_EXERC"])
        df = df[df["_months"].isin([3, 12])]
    else:
        df["_months"] = 0
    if df.empty:
        return 0
    df["_months"] = df["_months"].astype(int)

    df = _keep_latest(df, ["CD_CVM", "DT_FIM_EXERC", "_months"])

    value = pd.to_numeric(df["VL_CONTA"], errors="coerce") * _scale(df["ESCALA_MOEDA"])
    df = df.assign(_value=value).dropna(subset=["_value"])

    rows: list[dict[str, object]] = []
    for d in _records(df):
        period = str(d["DT_FIM_EXERC"])
        rows.append(
            {
                "cd_cvm": int(str(d["CD_CVM"])),
                "dataset": dataset_key,
                "statement": statement,
                "scope": scope,
                "period": period,
                "period_months": int(str(d["_months"])),
                "fiscal_year": int(period[:4]),
                "account_code": str(d["CD_CONTA"]),
                "account_desc": str(d["DS_CONTA"]),
                "value": float(str(d["_value"])),
                "version": int(str(d["VERSAO"])),
            }
        )

    with session() as s:
        _upsert_companies(s, df)
        n = _upsert(
            s,
            Fact,
            rows,
            ["cd_cvm", "statement", "scope", "period", "period_months", "account_code"],
            ["value", "version", "account_desc", "fiscal_year", "dataset"],
        )
    return n


def _ingest_shares(zip_path: Path, dataset_key: str, year: int) -> int:
    """Parse composicao_capital (shares outstanding) from an extracted ZIP."""
    ds = DATASETS[dataset_key]
    member = ds.member_csv("composicao_capital", year)
    csv_path = download.extract_member(zip_path, member)
    if csv_path is None:
        return 0
    try:
        return _store_shares(csv_path)
    finally:
        csv_path.unlink(missing_ok=True)


def _store_shares(csv_path: Path) -> int:
    df = _read_csv(str(csv_path))
    if df.empty:
        return 0
    df = _keep_latest(df, ["CNPJ_CIA", "DT_REFER"])

    engine: Engine = get_engine()
    cnpj_to_cd: dict[str, int] = {}
    with engine.connect() as conn:
        from sqlalchemy import select

        for row in conn.execute(select(Company.cd_cvm, Company.cnpj)).all():
            cd_val = cast("int", row[0])
            cnpj_val = cast("str | None", row[1])
            if cnpj_val:
                cnpj_to_cd[_digits(cnpj_val)] = cd_val

    def num(v: object) -> float:
        series = pd.to_numeric(pd.Series([v]), errors="coerce").fillna(0.0)
        return float(cast("float", series.iloc[0]))

    rows: list[dict[str, object]] = []
    for d in _records(df):
        cd = cnpj_to_cd.get(_digits(str(d.get("CNPJ_CIA"))))
        if cd is None:
            continue
        ordin = num(d.get("QT_ACAO_ORDIN_CAP_INTEGR")) - num(d.get("QT_ACAO_ORDIN_TESOURO"))
        pref = num(d.get("QT_ACAO_PREF_CAP_INTEGR")) - num(d.get("QT_ACAO_PREF_TESOURO"))
        total = num(d.get("QT_ACAO_TOTAL_CAP_INTEGR")) - num(d.get("QT_ACAO_TOTAL_TESOURO"))
        rows.append(
            {
                "cd_cvm": cd,
                "period": str(d["DT_REFER"]),
                "total": float(total),
                "ordinary": float(ordin),
                "preferred": float(pref),
            }
        )

    with session() as s:
        return _upsert(
            s, Shares, rows, ["cd_cvm", "period"], ["total", "ordinary", "preferred"]
        )


def ingest_ipe(year: int) -> int:
    """Parse the IPE document feed (fatos relevantes, comunicados) for a year."""
    with download.temp_dataset("ipe", year) as zip_path:
        csv_path = download.extract_member(zip_path, f"ipe_cia_aberta_{year}.csv")
        if csv_path is None:
            return 0
        df = _read_csv(str(csv_path))
    if df.empty or "Codigo_CVM" not in df.columns:
        return 0

    rows: list[dict[str, object]] = []
    for d in _records(df):
        cd_raw = str(d.get("Codigo_CVM") or "").strip()
        if not cd_raw.isdigit():
            continue
        rows.append(
            {
                "cd_cvm": int(cd_raw),
                "category": d.get("Categoria"),
                "doc_type": d.get("Tipo"),
                "subject": d.get("Assunto"),
                "ref_date": d.get("Data_Referencia"),
                "deliver_date": d.get("Data_Entrega"),
                "url": d.get("Link_Download"),
                "protocol": d.get("Protocolo_Entrega"),
            }
        )

    with session() as s:
        return _upsert(
            s,
            Document,
            rows,
            ["protocol", "url"],
            ["cd_cvm", "category", "doc_type", "subject", "ref_date", "deliver_date"],
        )


def ingest_cad() -> int:
    """Enrich companies with sector/situation from the CAD registry."""
    with download.temp_dataset("cad") as csv_path:
        df = _read_csv(str(csv_path))
    if df.empty or "CD_CVM" not in df.columns:
        return 0
    df = df.dropna(subset=["CD_CVM"])
    df = df[df["CD_CVM"].str.strip() != ""]

    rows: list[dict[str, object]] = []
    for d in _records(df):
        rows.append(
            {
                "cd_cvm": int(str(d["CD_CVM"])),
                "name": d.get("DENOM_SOCIAL") or d.get("DENOM_COMERC") or "",
                "cnpj": d.get("CNPJ_CIA"),
                "sector": d.get("SETOR_ATIV"),
                "situation": d.get("SIT"),
            }
        )

    with session() as s:
        return _upsert(s, Company, rows, ["cd_cvm"], ["sector", "situation", "cnpj"])
