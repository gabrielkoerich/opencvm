"""SQLAlchemy 2.0 engine + ORM models for the CVM store.

SQLite is configured for safe concurrent access from multiple Docker workers:
WAL journaling (readers never block the single writer) and a generous
``busy_timeout`` so colliding writers wait-and-retry instead of erroring.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from . import config


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__: str = "companies"

    cd_cvm: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj: Mapped[str | None] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    sector: Mapped[str | None] = mapped_column(String)
    situation: Mapped[str | None] = mapped_column(String)

    tickers: Mapped[list[Ticker]] = relationship(back_populates="company")


class Ticker(Base):
    __tablename__: str = "tickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cd_cvm: Mapped[int] = mapped_column(ForeignKey("companies.cd_cvm"), index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str | None] = mapped_column(String)  # ON / PN / UNT
    source: Mapped[str] = mapped_column(String, default="b3")

    company: Mapped[Company] = relationship(back_populates="tickers")

    __table_args__: tuple[object, ...] = (UniqueConstraint("ticker", name="uq_ticker"),)


class Fact(Base):
    """One reported account line, long format."""

    __tablename__: str = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cd_cvm: Mapped[int] = mapped_column(Integer, index=True)
    dataset: Mapped[str] = mapped_column(String)  # dfp / itr
    statement: Mapped[str] = mapped_column(String)  # DRE / BPA / BPP / DFC_* / DVA
    scope: Mapped[str] = mapped_column(String)  # con / ind
    period: Mapped[str] = mapped_column(String, index=True)  # DT_FIM_EXERC (YYYY-MM-DD)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    account_code: Mapped[str] = mapped_column(String, index=True)
    account_desc: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)  # already scaled to BRL units
    version: Mapped[int] = mapped_column(Integer)

    __table_args__: tuple[object, ...] = (
        UniqueConstraint(
            "cd_cvm",
            "statement",
            "scope",
            "period",
            "account_code",
            name="uq_fact",
        ),
        Index("ix_fact_lookup", "cd_cvm", "statement", "scope", "fiscal_year"),
    )


class Shares(Base):
    __tablename__: str = "shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cd_cvm: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(String)
    total: Mapped[float] = mapped_column(Float)
    ordinary: Mapped[float | None] = mapped_column(Float)
    preferred: Mapped[float | None] = mapped_column(Float)

    __table_args__: tuple[object, ...] = (
        UniqueConstraint("cd_cvm", "period", name="uq_shares"),
    )


class Document(Base):
    """An IPE feed entry (fato relevante, comunicado, etc.)."""

    __tablename__: str = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cd_cvm: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str | None] = mapped_column(String, index=True)
    doc_type: Mapped[str | None] = mapped_column(String)
    subject: Mapped[str | None] = mapped_column(String)
    ref_date: Mapped[str | None] = mapped_column(String, index=True)
    deliver_date: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    protocol: Mapped[str | None] = mapped_column(String)

    __table_args__: tuple[object, ...] = (
        UniqueConstraint("protocol", "url", name="uq_document"),
    )


class Indicator(Base):
    """Computed fundamental indicator, long format (price-based ones live-computed)."""

    __tablename__: str = "indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cd_cvm: Mapped[int] = mapped_column(Integer, index=True)
    scope: Mapped[str] = mapped_column(String)
    period: Mapped[str] = mapped_column(String, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[float | None] = mapped_column(Float)

    __table_args__: tuple[object, ...] = (
        UniqueConstraint("cd_cvm", "scope", "period", "name", name="uq_indicator"),
    )


class SyncMeta(Base):
    """Key/value sync bookkeeping; ``version`` drives the read cache + ETags."""

    __tablename__: str = "sync_meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def _configure_sqlite(dbapi_conn: sqlite3.Connection, _: object) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def get_engine() -> Engine:
    global _engine, _Session
    if _engine is None:
        config.ensure_dirs()
        _engine = create_engine(config.DB_URL, future=True)
        if _engine.dialect.name == "sqlite":
            event.listen(_engine, "connect", _configure_sqlite)
        _Session = sessionmaker(bind=_engine, future=True)
    return _engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())


@contextmanager
def session() -> Iterator[Session]:
    get_engine()
    assert _Session is not None
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
