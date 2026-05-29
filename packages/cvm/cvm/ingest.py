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
from typing import cast

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import download
from .datasets import DATASETS
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


def ingest_statement(dataset_key: str, statement: str, scope: str, year: int) -> int:
    """Download (cached), parse and upsert one statement/scope/year shard."""
    ds = DATASETS[dataset_key]
    zip_path, _ = download.download_dataset(dataset_key, year)
    member = ds.statement_csv(statement, scope, year)
    csv_path = download.extract_member(zip_path, member)
    if csv_path is None:
        return 0

    df = _read_csv(str(csv_path))
    if df.empty or "CD_CONTA" not in df.columns:
        return 0

    df = _keep_latest(df, ["CD_CVM", "DT_FIM_EXERC"])
    df = df.dropna(subset=["CD_CVM", "DT_FIM_EXERC", "CD_CONTA", "VL_CONTA"])
    df = df[df["CD_CVM"].str.strip() != ""]

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
            ["cd_cvm", "statement", "scope", "period", "account_code"],
            ["value", "version", "account_desc", "fiscal_year", "dataset"],
        )
    return n


def ingest_shares(dataset_key: str, year: int) -> int:
    """Parse composicao_capital (shares outstanding) from a DFP/ITR zip."""
    ds = DATASETS[dataset_key]
    zip_path, _ = download.download_dataset(dataset_key, year)
    member = ds.member_csv("composicao_capital", year)
    csv_path = download.extract_member(zip_path, member)
    if csv_path is None:
        return 0

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
    zip_path, _ = download.download_dataset("ipe", year)
    member = f"ipe_cia_aberta_{year}.csv"
    csv_path = download.extract_member(zip_path, member)
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
    zip_path, _ = download.download_dataset("cad")
    df = _read_csv(str(zip_path))
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
        return _upsert(
            s, Company, rows, ["cd_cvm"], ["sector", "situation", "cnpj"]
        )
