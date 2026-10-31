"""Règlement des recommandations : résultats et cotes de clôture depuis football-data.co.uk (gratuit)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from edgebet.betting.odds import devig
from edgebet.config import Settings
from edgebet.db import repo
from edgebet.db.session import session_scope
from edgebet.schema import OUTCOMES, odds_cols, slug
from edgebet.sports.football.football_data_uk import load_history, season_start_years

log = logging.getLogger(__name__)


def _find_match(history: pd.DataFrame, rec) -> pd.Series | None:
    exact = history[history["match_id"] == rec.match_id]
    if not exact.empty:
        return exact.iloc[0]
    # match reporté ou décalage de date : même affiche à ± 3 jours
    cand = history[(history["league"] == rec.league) & (history["home"].map(slug) == slug(rec.home)) & (history["away"].map(slug) == slug(rec.away))]
    if cand.empty:
        return None
    delta = (cand["date"] - pd.Timestamp(rec.kickoff)).abs()
    cand = cand[delta <= pd.Timedelta(days=3)]
    return None if cand.empty else cand.loc[delta.loc[cand.index].idxmin()]


def run_settle(s: Settings, now: datetime | None = None, history_override: pd.DataFrame | None = None, grace_hours: int = 3) -> dict:
    tz = ZoneInfo(s.timezone)
    now = now or datetime.now(tz)
    cutoff = now.replace(tzinfo=None) - timedelta(hours=grace_hours)
    history = history_override if history_override is not None else load_history(
        s.league_list, season_start_years(2), s.raw_dir, download_missing=True, refresh_current=True,
    )
    settled, still_open = 0, 0
    with session_scope(s.db_url) as session:
        run = repo.start_run(session, "settle")
        for rec in repo.open_recommendations_before(session, cutoff):
            row = _find_match(history, rec) if not history.empty else None
            if row is None or pd.isna(row.get("result")):
                still_open += 1
                continue
            close_cols = odds_cols("psc")
            closing = row[close_cols].to_numpy(dtype=float) if all(c in row.index for c in close_cols) else None
            p_close = None
            closing_odds = None
            if closing is not None and not np.isnan(closing).any():
                j = OUTCOMES.index(rec.selection)
                p_close = float(devig(closing, s.devig_method)[j])
                closing_odds = float(closing[j])
            repo.settle_recommendation(
                session, rec, result=str(row["result"]), score=f"{int(row['hg'])}-{int(row['ag'])}",
                closing_fair_prob=p_close, closing_odds=closing_odds, bankroll_start=s.bankroll,
            )
            settled += 1
        msg = f"{settled} réglés, {still_open} en attente"
        repo.finish_run(session, run, "ok", msg, n_matches=settled)
    log.info("Règlement : %s", msg)
    return {"settled": settled, "still_open": still_open, "message": msg}
