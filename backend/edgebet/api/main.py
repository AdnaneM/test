"""API HTTP (FastAPI) consommée par la PWA et par n8n."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from edgebet import __version__
from edgebet.api import schemas
from edgebet.config import Settings, get_settings
from edgebet.db import repo
from edgebet.db.session import init_db, session_scope
from edgebet.pipeline.daily import run_daily
from edgebet.pipeline.settle import run_settle
from edgebet.schema import LEAGUES
from edgebet.serialize import rec_to_dict, run_to_dict

log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db(get_settings().db_url)
    yield


app = FastAPI(title="EdgeBet API", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def require_key(x_api_key: str | None = Header(default=None), s: Settings = Depends(get_settings)) -> None:
    if s.api_key and x_api_key != s.api_key:
        raise HTTPException(status_code=401, detail="Clé API invalide")


@app.get("/api/health", response_model=schemas.HealthOut)
def health() -> dict:
    return {"status": "ok", "version": __version__, "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/grid", response_model=schemas.GridOut)
def grid(day: date | None = Query(default=None, alias="date"), s: Settings = Depends(get_settings)) -> dict:
    day = day or date.today()
    with session_scope(s.db_url) as session:
        recs = repo.recommendations_for_day(session, day, s.horizon_hours)
        items = [rec_to_dict(r, s) for r in recs]
        bankroll = repo.current_balance(session, s.bankroll)
        runs = repo.list_runs(session, 1)
    generated = runs[0].finished_at.isoformat(timespec="seconds") if runs and runs[0].finished_at else None
    active = [i for i in items if i["decision"] != "skipped"]
    summary = {
        "n_bets": len(active),
        "total_stake": round(sum(i["stake"] for i in active), 2),
        "avg_edge": round(sum(i["edge"] for i in active) / len(active), 4) if active else 0.0,
    }
    return {"date": day.isoformat(), "generated_at": generated, "bankroll": bankroll, "currency": "EUR", "summary": summary, "items": items}


@app.get("/api/recommendations", response_model=schemas.ListOut)
def recommendations(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    decision: str | None = None,
    outcome: str | None = None,
    limit: int = Query(default=500, le=5000),
    s: Settings = Depends(get_settings),
) -> dict:
    with session_scope(s.db_url) as session:
        recs = repo.list_recommendations(session, date_from, date_to, decision, outcome, limit)
        items = [rec_to_dict(r, s) for r in recs]
    return {"items": items, "count": len(items)}


@app.post("/api/recommendations/{rec_id}/mark", response_model=schemas.RecommendationOut, dependencies=[Depends(require_key)])
def mark(rec_id: int, body: schemas.MarkIn, s: Settings = Depends(get_settings)) -> dict:
    with session_scope(s.db_url) as session:
        rec = repo.get_recommendation(session, rec_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="Recommandation introuvable")
        repo.mark_recommendation(session, rec, body.decision, body.stake, body.odds)
        return rec_to_dict(rec, s)


@app.get("/api/stats", response_model=schemas.StatsOut)
def stats(s: Settings = Depends(get_settings)) -> dict:
    with session_scope(s.db_url) as session:
        return repo.stats(session, s.bankroll, {c: lg.name for c, lg in LEAGUES.items()})


@app.get("/api/runs", response_model=schemas.RunsOut)
def runs(limit: int = Query(default=20, le=200), s: Settings = Depends(get_settings)) -> dict:
    with session_scope(s.db_url) as session:
        return {"items": [run_to_dict(r) for r in repo.list_runs(session, limit)]}


@app.post("/api/pipeline/run", response_model=schemas.DailyRunOut, dependencies=[Depends(require_key)])
def pipeline_run(notify: bool = False, s: Settings = Depends(get_settings)) -> dict:
    try:
        res = run_daily(s, notify=notify)
    except Exception as exc:
        log.exception("Pipeline quotidien en échec")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "run_id": res.run_id, "n_events": res.n_events, "n_fixtures": res.n_fixtures, "n_candidates": res.n_candidates,
        "n_recommendations": len(res.recommendations), "credits_remaining": res.credits_remaining,
        "unmatched_teams": res.unmatched_teams, "warnings": res.warnings, "message": res.message, "items": res.recommendations,
    }


@app.post("/api/pipeline/settle", response_model=schemas.SettleOut, dependencies=[Depends(require_key)])
def pipeline_settle(s: Settings = Depends(get_settings)) -> dict:
    try:
        return run_settle(s)
    except Exception as exc:
        log.exception("Règlement en échec")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
