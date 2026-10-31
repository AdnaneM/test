from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from edgebet.api.main import app
from edgebet.betting.value import BetCandidate
from edgebet.config import Settings, get_settings
from edgebet.data.odds_api import events_to_frame, pivot_h2h
from edgebet.db import repo
from edgebet.db.session import session_scope
from edgebet.features.build import FeatureConfig, build_feature_frame
from edgebet.notify.telegram import format_bet, keyboard_for, parse_callback
from edgebet.pipeline.daily import build_fixtures, bundle_path, run_daily
from edgebet.pipeline.settle import run_settle
from edgebet.pipeline.train import train_bundle
from edgebet.serialize import rec_to_dict

SAMPLE_EVENT = {
    "id": "evt1", "sport_key": "soccer_france_ligue_one", "commence_time": "2026-11-01T19:45:00Z",
    "home_team": "Paris Saint Germain", "away_team": "Olympique Marseille",
    "bookmakers": [
        {"key": "pinnacle", "title": "Pinnacle", "last_update": "2026-11-01T08:00:00Z", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Paris Saint Germain", "price": 1.95}, {"name": "Olympique Marseille", "price": 4.2}, {"name": "Draw", "price": 3.7}]}]},
        {"key": "winamax_fr", "title": "Winamax", "last_update": "2026-11-01T08:00:00Z", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Paris Saint Germain", "price": 2.05}, {"name": "Olympique Marseille", "price": 3.9}, {"name": "Draw", "price": 3.5}]}]},
    ],
}


@pytest.fixture()
def settings(tmp_path):
    s = Settings(data_dir=tmp_path / "data", api_key="secret", bankroll=100.0, leagues="F1", bookmakers="winamax_fr",
                 telegram_bot_token="", telegram_chat_id="", _env_file=None)
    app.dependency_overrides[get_settings] = lambda: s
    yield s
    app.dependency_overrides.clear()


def _candidate(kickoff: datetime) -> BetCandidate:
    return BetCandidate(match_id="F1:2026-11-01:paris-sg:marseille", league="F1", home="Paris SG", away="Marseille",
                        kickoff=kickoff.isoformat(timespec="minutes"), market="1X2", selection="H", selection_label="Victoire domicile",
                        p_model=0.52, odds=2.05, bookmaker="winamax_fr", edge=0.066, kelly=0.063, stake=1.5, risk=2,
                        p_sharp=0.49, fair_odds_sharp=2.04, edge_vs_sharp=0.0045, disagreement=0.02, components={"gbm": 0.5, "dc": 0.53, "market": 0.49})


def test_odds_api_parsing():
    long = events_to_frame([SAMPLE_EVENT], "F1")
    assert len(long) == 6 and set(long["outcome"]) == {"H", "D", "A"}
    wide = pivot_h2h(long)
    assert len(wide) == 2
    pin = wide[wide["bookmaker"] == "pinnacle"].iloc[0]
    assert pin["odds_h"] == 1.95 and pin["odds_d"] == 3.7 and pin["odds_a"] == 4.2


def test_build_fixtures_resolves_names(settings):
    history = pd.DataFrame({"league": ["F1"], "season": ["2025-26"], "home": ["Paris SG"], "away": ["Marseille"], "date": [pd.Timestamp("2025-09-01")]})
    fixtures, prices, sharp, snaps, unmatched = build_fixtures({"F1": [SAMPLE_EVENT]}, history, settings)
    assert unmatched == []
    assert len(fixtures) == 1 and fixtures.iloc[0]["home"] == "Paris SG" and fixtures.iloc[0]["away"] == "Marseille"
    mid = fixtures.iloc[0]["match_id"]
    assert mid.startswith("F1:2026-11-01:paris-sg:marseille")
    assert fixtures.iloc[0]["date"].hour == 20  # 19:45 UTC = 20:45 Paris
    assert "winamax_fr" in prices[mid] and np.allclose(sharp[mid], [1.95, 3.7, 4.2])
    assert len(snaps) == 2


def test_api_grid_mark_stats(settings):
    kickoff = datetime(2026, 11, 1, 20, 45)
    with session_scope(settings.db_url) as session:
        run = repo.start_run(session, "daily")
        recs = repo.upsert_recommendations(session, run.id, [_candidate(kickoff)])
        repo.finish_run(session, run, "ok", "test", n_matches=1, n_recommendations=1, credits_remaining=480)
        rec_id = recs[0].id
        # ré-exécution le même jour : pas de doublon
        again = repo.upsert_recommendations(session, run.id, [_candidate(kickoff)])
        assert again[0].id == rec_id
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    grid = client.get("/api/grid", params={"date": "2026-11-01"}).json()
    assert grid["summary"]["n_bets"] == 1 and grid["items"][0]["pick_label"] == "Paris SG"
    assert grid["items"][0]["bookmaker_label"] == "Winamax" and grid["items"][0]["bookmaker_url"]
    assert client.post(f"/api/recommendations/{rec_id}/mark", json={"decision": "played"}).status_code == 401
    r = client.post(f"/api/recommendations/{rec_id}/mark", json={"decision": "played", "stake": 2.0}, headers={"X-API-Key": "secret"})
    assert r.status_code == 200 and r.json()["decision"] == "played" and r.json()["stake_taken"] == 2.0
    runs = client.get("/api/runs").json()["items"]
    assert runs[0]["credits_remaining"] == 480
    # règlement : PSG gagne 2-1, clôture Pinnacle 1.90 / 3.8 / 4.5
    history = pd.DataFrame([{
        "match_id": "F1:2026-11-01:paris-sg:marseille", "league": "F1", "home": "Paris SG", "away": "Marseille",
        "date": pd.Timestamp(kickoff), "hg": 2, "ag": 1, "result": "H", "odds_psc_h": 1.9, "odds_psc_d": 3.8, "odds_psc_a": 4.5,
    }])
    res = run_settle(settings, now=kickoff + timedelta(hours=6), history_override=history)
    assert res["settled"] == 1
    stats = client.get("/api/stats").json()
    assert stats["n_played"] == 1 and stats["n_won"] == 1 and abs(stats["pnl"] - 2.1) < 1e-9
    assert stats["bankroll_current"] == 102.1 and stats["bankroll_curve"][-1]["balance"] == 102.1
    hist = client.get("/api/recommendations", params={"outcome": "won"}).json()
    assert hist["count"] == 1 and hist["items"][0]["clv"] is not None and hist["items"][0]["score"] == "2-1"
    with session_scope(settings.db_url) as session:
        d = rec_to_dict(repo.get_recommendation(session, rec_id), settings)
    text = format_bet(d)
    assert "Paris SG" in text and "Winamax" in text
    kb = keyboard_for(d)
    assert "Annuler" in kb["inline_keyboard"][0][0]["text"]
    assert parse_callback(f"mark:{rec_id}:skipped") == (rec_id, "skipped") and parse_callback("x") is None


def test_run_daily_end_to_end_with_synthetic_model(settings, league_df):
    df, _ = league_df
    df = df.copy()
    # on rebaptise deux équipes synthétiques pour matcher l'événement The Odds API
    df["home"] = df["home"].replace({"Team 00": "Paris SG", "Team 01": "Marseille"})
    df["away"] = df["away"].replace({"Team 00": "Paris SG", "Team 01": "Marseille"})
    cfg = FeatureConfig(dc_refit_days=7, dc_window_days=800, dc_min_matches=120)
    feats, _ = build_feature_frame(df, cfg)
    train_bundle(feats, cfg, min_matches_in_season=100).save(bundle_path(settings))
    settings.require_sharp_agreement = False
    now = datetime(2026, 11, 1, 9, 0)
    # cotes très généreuses (somme des probabilités implicites < 1) : au moins une issue a une edge positive
    generous = {**SAMPLE_EVENT, "bookmakers": [SAMPLE_EVENT["bookmakers"][0], {
        "key": "winamax_fr", "title": "Winamax", "last_update": "2026-11-01T08:00:00Z",
        "markets": [{"key": "h2h", "outcomes": [{"name": "Paris Saint Germain", "price": 3.0},
                                                 {"name": "Olympique Marseille", "price": 5.0}, {"name": "Draw", "price": 4.0}]}]}]}
    res = run_daily(settings, now=now.astimezone(), notify=False, events_override={"F1": [generous]}, history_override=df)
    assert res.n_fixtures == 1 and res.unmatched_teams == []
    assert len(res.recommendations) == 1
    rec = res.recommendations[0]
    assert rec["bookmaker"] == "winamax_fr" and rec["odds"] in (3.0, 4.0, 5.0) and rec["edge"] > 0
    assert rec["id"] is not None
    client = TestClient(app)
    grid = client.get("/api/grid", params={"date": "2026-11-01"}).json()
    assert grid["summary"]["n_bets"] == 1
