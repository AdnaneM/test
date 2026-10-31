"""Modèle de données (SQLAlchemy 2.0). SQLite par défaut, PostgreSQL possible via EDGEBET_DATABASE_URL."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20))  # daily | settle | train
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | error
    n_matches: Mapped[int] = mapped_column(Integer, default=0)
    n_recommendations: Mapped[int] = mapped_column(Integer, default=0)
    credits_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=True)
    match_id: Mapped[str] = mapped_column(String(120), index=True)
    sport: Mapped[str] = mapped_column(String(20), default="football")
    league: Mapped[str] = mapped_column(String(10), index=True)
    home: Mapped[str] = mapped_column(String(80))
    away: Mapped[str] = mapped_column(String(80))
    kickoff: Mapped[datetime] = mapped_column(DateTime, index=True)
    market: Mapped[str] = mapped_column(String(10), default="1X2")
    selection: Mapped[str] = mapped_column(String(10))
    selection_label: Mapped[str] = mapped_column(String(40))
    p_model: Mapped[float] = mapped_column(Float)
    p_sharp: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds: Mapped[float] = mapped_column(Float)
    bookmaker: Mapped[str] = mapped_column(String(30))
    fair_odds_sharp: Mapped[float | None] = mapped_column(Float, nullable=True)
    edge: Mapped[float] = mapped_column(Float)
    edge_vs_sharp: Mapped[float | None] = mapped_column(Float, nullable=True)
    kelly: Mapped[float] = mapped_column(Float)
    stake: Mapped[float] = mapped_column(Float)
    risk: Mapped[int] = mapped_column(Integer)
    components_json: Mapped[str] = mapped_column(Text, default="{}")
    decision: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | played | skipped
    outcome: Mapped[str] = mapped_column(String(10), default="open", index=True)  # open | won | lost | void
    odds_taken: Mapped[float | None] = mapped_column(Float, nullable=True)
    stake_taken: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[str | None] = mapped_column(String(2), nullable=True)
    score: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    clv: Mapped[float | None] = mapped_column(Float, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=True)
    match_id: Mapped[str] = mapped_column(String(120), index=True)
    league: Mapped[str] = mapped_column(String(10))
    home: Mapped[str] = mapped_column(String(80))
    away: Mapped[str] = mapped_column(String(80))
    kickoff: Mapped[datetime] = mapped_column(DateTime)
    bookmaker: Mapped[str] = mapped_column(String(30))
    market: Mapped[str] = mapped_column(String(10), default="h2h")
    odds_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_d: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_a: Mapped[float | None] = mapped_column(Float, nullable=True)


class BankrollEntry(Base):
    __tablename__ = "bankroll"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    delta: Mapped[float] = mapped_column(Float)
    balance: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(String(200), default="")
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"), nullable=True)
