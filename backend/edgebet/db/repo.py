"""Accès aux données : recommandations, règlement, bankroll, statistiques."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edgebet.betting.value import BetCandidate
from edgebet.db.models import BankrollEntry, OddsSnapshot, PipelineRun, Recommendation
from edgebet.models.calibration import calibration_table


def start_run(session: Session, kind: str) -> PipelineRun:
    run = PipelineRun(kind=kind, started_at=datetime.now(), status="running")
    session.add(run)
    session.flush()
    return run


def finish_run(session: Session, run: PipelineRun, status: str = "ok", message: str = "", **fields) -> PipelineRun:
    run.status = status
    run.message = (message or "")[:4000]
    run.finished_at = datetime.now()
    for k, v in fields.items():
        setattr(run, k, v)
    session.flush()
    return run


def list_runs(session: Session, limit: int = 20) -> list[PipelineRun]:
    return list(session.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit)))


def save_odds_snapshots(session: Session, run_id: int | None, rows: list[dict]) -> int:
    objs = [OddsSnapshot(run_id=run_id, **r) for r in rows]
    session.add_all(objs)
    session.flush()
    return len(objs)


def upsert_recommendations(session: Session, run_id: int | None, candidates: list[BetCandidate]) -> list[Recommendation]:
    """Crée les recommandations ; si une recommandation en attente existe déjà pour le même match et la
    même issue, met à jour la cote, la mise et l'edge au lieu de dupliquer."""
    out: list[Recommendation] = []
    for c in candidates:
        kickoff = datetime.fromisoformat(c.kickoff) if isinstance(c.kickoff, str) else c.kickoff
        existing = session.scalars(
            select(Recommendation).where(
                Recommendation.match_id == c.match_id,
                Recommendation.selection == c.selection,
                Recommendation.outcome == "open",
            )
        ).first()
        payload = dict(
            run_id=run_id, match_id=c.match_id, league=c.league, home=c.home, away=c.away, kickoff=kickoff,
            market=c.market, selection=c.selection, selection_label=c.selection_label, p_model=c.p_model,
            p_sharp=c.p_sharp, odds=c.odds, bookmaker=c.bookmaker, fair_odds_sharp=c.fair_odds_sharp, edge=c.edge,
            edge_vs_sharp=c.edge_vs_sharp, kelly=c.kelly, stake=c.stake, risk=c.risk,
            components_json=json.dumps(c.components),
        )
        if existing is not None:
            if existing.decision == "pending":
                for k, v in payload.items():
                    setattr(existing, k, v)
            out.append(existing)
        else:
            rec = Recommendation(**payload)
            session.add(rec)
            out.append(rec)
    session.flush()
    return out


def get_recommendation(session: Session, rec_id: int) -> Recommendation | None:
    return session.get(Recommendation, rec_id)


def recommendations_for_day(session: Session, day: date, horizon_hours: int = 36) -> list[Recommendation]:
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(hours=max(24, horizon_hours))
    stmt = (
        select(Recommendation)
        .where(Recommendation.kickoff >= start, Recommendation.kickoff < end)
        .order_by(Recommendation.kickoff, Recommendation.edge.desc())
    )
    return list(session.scalars(stmt))


def list_recommendations(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    decision: str | None = None,
    outcome: str | None = None,
    limit: int = 500,
) -> list[Recommendation]:
    stmt = select(Recommendation)
    if date_from:
        stmt = stmt.where(Recommendation.kickoff >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Recommendation.kickoff < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    if decision:
        stmt = stmt.where(Recommendation.decision == decision)
    if outcome:
        stmt = stmt.where(Recommendation.outcome == outcome)
    stmt = stmt.order_by(Recommendation.kickoff.desc()).limit(limit)
    return list(session.scalars(stmt))


def open_recommendations_before(session: Session, before: datetime) -> list[Recommendation]:
    stmt = select(Recommendation).where(Recommendation.outcome == "open", Recommendation.kickoff < before)
    return list(session.scalars(stmt))


def mark_recommendation(
    session: Session, rec: Recommendation, decision: str, stake: float | None = None, odds: float | None = None
) -> Recommendation:
    if decision not in ("pending", "played", "skipped"):
        raise ValueError("decision doit valoir pending, played ou skipped")
    rec.decision = decision
    rec.decided_at = datetime.now() if decision != "pending" else None
    if decision == "played":
        rec.stake_taken = float(stake) if stake is not None else rec.stake
        rec.odds_taken = float(odds) if odds is not None else rec.odds
    else:
        rec.stake_taken = None
        rec.odds_taken = None
    session.flush()
    return rec


def settle_recommendation(
    session: Session, rec: Recommendation, result: str, score: str | None, closing_fair_prob: float | None,
    closing_odds: float | None, bankroll_start: float,
) -> Recommendation:
    """Règle un pari (gagné/perdu), calcule le P&L (réel si joué, théorique sinon) et le CLV."""
    won = result == rec.selection
    rec.result = result
    rec.score = score
    rec.outcome = "won" if won else "lost"
    stake = rec.stake_taken if rec.decision == "played" and rec.stake_taken is not None else rec.stake
    odds = rec.odds_taken if rec.decision == "played" and rec.odds_taken is not None else rec.odds
    rec.pnl = round(stake * (odds - 1.0), 2) if won else round(-stake, 2)
    rec.closing_odds = closing_odds
    rec.clv = None if closing_fair_prob is None or np.isnan(closing_fair_prob) else round(odds * closing_fair_prob - 1.0, 4)
    rec.settled_at = datetime.now()
    if rec.decision == "played":
        add_bankroll_entry(session, rec.pnl, f"{rec.home} - {rec.away} : {rec.selection} @ {odds}", rec.id, bankroll_start)
    session.flush()
    return rec


def current_balance(session: Session, bankroll_start: float) -> float:
    last = session.scalars(select(BankrollEntry).order_by(BankrollEntry.id.desc()).limit(1)).first()
    return float(last.balance) if last else float(bankroll_start)


def add_bankroll_entry(session: Session, delta: float, note: str, rec_id: int | None, bankroll_start: float) -> BankrollEntry:
    balance = current_balance(session, bankroll_start) + float(delta)
    entry = BankrollEntry(delta=float(delta), balance=round(balance, 2), note=note[:200], recommendation_id=rec_id)
    session.add(entry)
    session.flush()
    return entry


def bankroll_curve(session: Session, bankroll_start: float) -> list[dict]:
    entries = list(session.scalars(select(BankrollEntry).order_by(BankrollEntry.at, BankrollEntry.id)))
    curve: list[dict] = []
    first_date = entries[0].at.date() if entries else date.today()
    curve.append({"date": (first_date - timedelta(days=1)).isoformat(), "balance": float(bankroll_start)})
    by_day: dict[str, float] = {}
    for e in entries:
        by_day[e.at.date().isoformat()] = float(e.balance)
    curve.extend({"date": d, "balance": b} for d, b in sorted(by_day.items()))
    return curve


def _summary(recs: list[Recommendation]) -> dict:
    staked = sum((r.stake_taken or 0.0) for r in recs)
    pnl = sum((r.pnl or 0.0) for r in recs)
    return {"n": len(recs), "staked": round(staked, 2), "pnl": round(pnl, 2), "roi": (pnl / staked) if staked > 0 else None}


def stats(session: Session, bankroll_start: float, league_names: dict[str, str]) -> dict:
    settled = list(session.scalars(select(Recommendation).where(Recommendation.outcome.in_(["won", "lost"]))))
    played = [r for r in settled if r.decision == "played"]
    n_recommended = session.scalar(select(func.count(Recommendation.id))) or 0
    won = [r for r in played if r.outcome == "won"]
    staked = sum(r.stake_taken or 0.0 for r in played)
    pnl = sum(r.pnl or 0.0 for r in played)
    clvs = [r.clv for r in settled if r.clv is not None]
    by_league = []
    for lg in sorted({r.league for r in played}):
        s = _summary([r for r in played if r.league == lg])
        by_league.append({"league": lg, "league_name": league_names.get(lg, lg), **s})
    by_risk = []
    for rk in sorted({r.risk for r in played}):
        by_risk.append({"risk": rk, **_summary([r for r in played if r.risk == rk])})
    calib: list[dict] = []
    if len(settled) >= 10:
        p = np.array([r.p_model for r in settled], dtype=float)
        hit = np.array([1.0 if r.outcome == "won" else 0.0 for r in settled])
        calib = calibration_table(p, hit, bins=10).to_dict(orient="records")
    return {
        "bankroll_start": float(bankroll_start),
        "bankroll_current": round(current_balance(session, bankroll_start), 2),
        "n_recommended": int(n_recommended),
        "n_settled": len(settled),
        "n_played": len(played),
        "n_won": len(won),
        "hit_rate": (len(won) / len(played)) if played else None,
        "staked": round(staked, 2),
        "pnl": round(pnl, 2),
        "roi": (pnl / staked) if staked > 0 else None,
        "clv_mean": float(np.mean(clvs)) if clvs else None,
        "avg_odds": float(np.mean([r.odds_taken or r.odds for r in played])) if played else None,
        "by_league": by_league,
        "by_risk": by_risk,
        "bankroll_curve": bankroll_curve(session, bankroll_start),
        "calibration": calib,
    }
