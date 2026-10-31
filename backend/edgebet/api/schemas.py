"""Schémas Pydantic de l'API (contrat partagé avec la PWA)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str = "ok"
    version: str
    time: str


class RecommendationOut(BaseModel):
    id: int
    created_at: str | None
    match_id: str
    league: str
    league_name: str
    home: str
    away: str
    kickoff: str | None
    market: str
    selection: str
    selection_label: str
    pick_label: str
    p_model: float
    p_sharp: float | None
    odds: float
    bookmaker: str
    bookmaker_label: str
    bookmaker_url: str | None
    fair_odds_sharp: float | None
    edge: float
    edge_vs_sharp: float | None
    kelly: float
    stake: float
    risk: int
    components: dict[str, float]
    decision: str
    outcome: str
    odds_taken: float | None
    stake_taken: float | None
    result: str | None
    score: str | None
    pnl: float | None
    closing_odds: float | None
    clv: float | None


class GridSummary(BaseModel):
    n_bets: int
    total_stake: float
    avg_edge: float


class GridOut(BaseModel):
    date: str
    generated_at: str | None
    bankroll: float
    currency: str = "EUR"
    summary: GridSummary
    items: list[RecommendationOut]


class ListOut(BaseModel):
    items: list[RecommendationOut]
    count: int


class MarkIn(BaseModel):
    decision: Literal["pending", "played", "skipped"]
    stake: float | None = Field(default=None, ge=0)
    odds: float | None = Field(default=None, gt=1)


class RunOut(BaseModel):
    id: int
    kind: str
    started_at: str | None
    finished_at: str | None
    status: str
    n_matches: int
    n_recommendations: int
    credits_remaining: int | None
    message: str


class RunsOut(BaseModel):
    items: list[RunOut]


class StatsOut(BaseModel):
    bankroll_start: float
    bankroll_current: float
    n_recommended: int
    n_settled: int
    n_played: int
    n_won: int
    hit_rate: float | None
    staked: float
    pnl: float
    roi: float | None
    clv_mean: float | None
    avg_odds: float | None
    by_league: list[dict]
    by_risk: list[dict]
    bankroll_curve: list[dict]
    calibration: list[dict]


class DailyRunOut(BaseModel):
    run_id: int | None
    n_events: int
    n_fixtures: int
    n_candidates: int
    n_recommendations: int
    credits_remaining: int | None
    unmatched_teams: list[str]
    warnings: list[str]
    message: str
    items: list[RecommendationOut]


class SettleOut(BaseModel):
    settled: int
    still_open: int
    message: str
