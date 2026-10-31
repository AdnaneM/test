"""Sérialisation des recommandations vers le contrat JSON partagé par l'API, Telegram et la PWA."""

from __future__ import annotations

import json

from edgebet.config import Settings
from edgebet.data.odds_api import bookmaker_label
from edgebet.db.models import PipelineRun, Recommendation
from edgebet.schema import LEAGUES


def league_name(code: str) -> str:
    lg = LEAGUES.get(code)
    return lg.name if lg else code


def pick_label(selection: str, home: str, away: str) -> str:
    return {"H": home, "A": away, "D": "Match nul"}.get(selection, selection)


def rec_to_dict(rec: Recommendation, settings: Settings) -> dict:
    try:
        components = json.loads(rec.components_json or "{}")
    except json.JSONDecodeError:
        components = {}
    links = settings.bookmaker_link_map
    return {
        "id": rec.id,
        "created_at": rec.created_at.isoformat(timespec="seconds") if rec.created_at else None,
        "match_id": rec.match_id,
        "league": rec.league,
        "league_name": league_name(rec.league),
        "home": rec.home,
        "away": rec.away,
        "kickoff": rec.kickoff.isoformat(timespec="minutes") if rec.kickoff else None,
        "market": rec.market,
        "selection": rec.selection,
        "selection_label": rec.selection_label,
        "pick_label": pick_label(rec.selection, rec.home, rec.away),
        "p_model": rec.p_model,
        "p_sharp": rec.p_sharp,
        "odds": rec.odds,
        "bookmaker": rec.bookmaker,
        "bookmaker_label": bookmaker_label(rec.bookmaker),
        "bookmaker_url": links.get(rec.bookmaker),
        "fair_odds_sharp": rec.fair_odds_sharp,
        "edge": rec.edge,
        "edge_vs_sharp": rec.edge_vs_sharp,
        "kelly": rec.kelly,
        "stake": rec.stake,
        "risk": rec.risk,
        "components": components,
        "decision": rec.decision,
        "outcome": rec.outcome,
        "odds_taken": rec.odds_taken,
        "stake_taken": rec.stake_taken,
        "result": rec.result,
        "score": rec.score,
        "pnl": rec.pnl,
        "closing_odds": rec.closing_odds,
        "clv": rec.clv,
    }


def run_to_dict(run: PipelineRun) -> dict:
    return {
        "id": run.id,
        "kind": run.kind,
        "started_at": run.started_at.isoformat(timespec="seconds") if run.started_at else None,
        "finished_at": run.finished_at.isoformat(timespec="seconds") if run.finished_at else None,
        "status": run.status,
        "n_matches": run.n_matches,
        "n_recommendations": run.n_recommendations,
        "credits_remaining": run.credits_remaining,
        "message": run.message or "",
    }
