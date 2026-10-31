"""Pipeline quotidien : cotes du jour -> features -> prédictions -> value bets -> base -> notification."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from edgebet.betting.odds import devig
from edgebet.betting.value import BetCandidate, StakingPolicy, evaluate_match, select_daily
from edgebet.config import Settings
from edgebet.data.odds_api import OddsAPIClient, events_to_frame, pivot_h2h
from edgebet.data.teams import TeamResolver
from edgebet.db import repo
from edgebet.db.session import session_scope
from edgebet.features.build import DC_COLS, MKT_COLS, FeatureConfig, build_feature_frame
from edgebet.features.elo import EloConfig
from edgebet.models.bundle import ModelBundle
from edgebet.models.calibration import apply_temperature
from edgebet.models.ensemble import blend
from edgebet.schema import LEAGUES, make_match_id
from edgebet.serialize import rec_to_dict
from edgebet.sports.football.football_data_uk import (
    current_season_start,
    load_history,
    season_label,
    season_start_years,
)

log = logging.getLogger(__name__)


@dataclass
class DailyResult:
    run_id: int | None
    n_events: int
    n_fixtures: int
    n_candidates: int
    recommendations: list[dict]
    credits_remaining: int | None
    unmatched_teams: list[str]
    warnings: list[str] = field(default_factory=list)
    message: str = ""


def feature_config_from_settings(s: Settings) -> FeatureConfig:
    return FeatureConfig(
        dc_xi=s.dc_xi, dc_refit_days=s.dc_refit_days, dc_window_days=s.dc_window_days,
        dc_min_matches=s.dc_min_matches, devig_method=s.devig_method, elo=EloConfig(),
    )


def policy_from_settings(s: Settings, bankroll: float | None = None) -> StakingPolicy:
    return StakingPolicy(
        bankroll=bankroll if bankroll is not None else s.bankroll, kelly_fraction=s.kelly_fraction,
        max_stake_fraction=s.max_stake_fraction, min_edge=s.min_edge, min_odds=s.min_odds, max_odds=s.max_odds,
        min_probability=s.min_probability, require_sharp_agreement=s.require_sharp_agreement,
        sharp_tolerance=s.sharp_tolerance, max_bets_per_day=s.max_bets_per_day,
    )


def bundle_path(s: Settings):
    return s.models_dir / "bundle.joblib"


def load_bundle(s: Settings) -> ModelBundle:
    path = bundle_path(s)
    if not path.exists():
        raise RuntimeError(f"Modèle absent ({path}). Lancer d'abord : edgebet train")
    return ModelBundle.load(path)


def fetch_events(s: Settings, now_utc: datetime, client: OddsAPIClient | None = None) -> tuple[dict[str, list[dict]], int | None]:
    client = client or OddsAPIClient(s.odds_api_key)
    out: dict[str, list[dict]] = {}
    for code in s.league_list:
        lg = LEAGUES.get(code)
        if lg is None:
            log.warning("Ligue inconnue : %s", code)
            continue
        try:
            out[code] = client.odds(
                lg.odds_api_key, regions=s.odds_regions, markets=s.odds_markets,
                commence_from=now_utc, commence_to=now_utc + timedelta(hours=s.horizon_hours),
            )
        except Exception as exc:
            log.warning("Cotes indisponibles pour %s : %s", code, exc)
            out[code] = []
    return out, client.remaining


def build_fixtures(
    events_by_league: dict[str, list[dict]], history: pd.DataFrame, s: Settings, resolver: TeamResolver | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, np.ndarray]], dict[str, np.ndarray], list[dict], list[str]]:
    """Transforme les événements The Odds API en lignes de matchs à venir au schéma canonique.

    Retourne (fixtures, cotes par match et bookmaker, cotes sharp par match, lignes de snapshot, équipes non reconnues).
    """
    tz = ZoneInfo(s.timezone)
    resolver = resolver or TeamResolver.from_yaml()
    season = season_label(current_season_start())
    rows: list[dict] = []
    prices: dict[str, dict[str, np.ndarray]] = {}
    sharp: dict[str, np.ndarray] = {}
    snapshots: list[dict] = []
    unmatched: set[str] = set()
    recent_seasons = sorted(history["season"].unique())[-2:] if not history.empty else []
    for league, events in events_by_league.items():
        if not events:
            continue
        hist_lg = history[(history["league"] == league) & (history["season"].isin(recent_seasons))]
        candidates = sorted(set(hist_lg["home"]) | set(hist_lg["away"])) or None
        if candidates:
            resolver.add_known(candidates)
        wide = pivot_h2h(events_to_frame(events, league))
        for _event_id, grp in wide.groupby("event_id", sort=False):
            first = grp.iloc[0]
            home = resolver.resolve(first["home"], candidates)
            away = resolver.resolve(first["away"], candidates)
            if home is None or away is None:
                unmatched.update(n for n, r in ((first["home"], home), (first["away"], away)) if r is None)
                continue
            kickoff = pd.Timestamp(first["commence_time"]).tz_convert(tz).tz_localize(None)
            match_id = make_match_id(league, kickoff, home, away)
            by_book = {r["bookmaker"]: np.array([r["odds_h"], r["odds_d"], r["odds_a"]], dtype=float) for _, r in grp.iterrows()}
            sharp_odds = by_book.get(s.sharp_bookmaker)
            book_prices = {b: by_book[b] for b in s.bookmaker_list if b in by_book and not np.isnan(by_book[b]).any()}
            if not book_prices:
                continue
            row = {
                "match_id": match_id, "sport": "football", "league": league, "season": season, "date": kickoff,
                "home": home, "away": away, "hg": np.nan, "ag": np.nan, "result": None,
            }
            if sharp_odds is not None and not np.isnan(sharp_odds).any():
                row.update({"odds_sharp_h": sharp_odds[0], "odds_sharp_d": sharp_odds[1], "odds_sharp_a": sharp_odds[2]})
                sharp[match_id] = sharp_odds
            rows.append(row)
            prices[match_id] = book_prices
            for b, arr in by_book.items():
                snapshots.append({
                    "match_id": match_id, "league": league, "home": home, "away": away, "kickoff": kickoff.to_pydatetime(),
                    "bookmaker": b, "market": "h2h", "odds_h": _f(arr[0]), "odds_d": _f(arr[1]), "odds_a": _f(arr[2]),
                })
    fixtures = pd.DataFrame(rows)
    return fixtures, prices, sharp, snapshots, sorted(unmatched)


def _f(v) -> float | None:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def predict_fixtures(
    history: pd.DataFrame, fixtures: pd.DataFrame, bundle: ModelBundle, cfg: FeatureConfig,
) -> tuple[pd.DataFrame, dict[str, np.ndarray], np.ndarray]:
    """Features causales sur historique + matchs à venir, puis probabilités finales des matchs à venir."""
    df = pd.concat([history, fixtures], ignore_index=True, sort=False)
    features, _ = build_feature_frame(df, cfg)
    rows = features[features["match_id"].isin(set(fixtures["match_id"]))].copy()
    rows = rows.set_index("match_id").loc[fixtures["match_id"]].reset_index()
    p_gbm = apply_temperature(bundle.gbm.predict_proba(rows), bundle.temperature)
    comps = {"gbm": p_gbm, "dc": rows[DC_COLS[:3]].to_numpy(dtype=float), "market": rows[MKT_COLS].to_numpy(dtype=float)}
    p_final = blend(comps, bundle.weights)
    return rows, comps, p_final


def make_candidates(
    rows: pd.DataFrame, comps: dict[str, np.ndarray], p_final: np.ndarray, prices: dict[str, dict[str, np.ndarray]],
    sharp: dict[str, np.ndarray], policy: StakingPolicy, devig_method: str,
) -> list[BetCandidate]:
    out: list[BetCandidate] = []
    for i, r in rows.reset_index(drop=True).iterrows():
        mid = r["match_id"]
        if np.isnan(p_final[i]).any():
            continue
        p_sharp = devig(sharp[mid], devig_method) if mid in sharp else None
        played = min(float(r.get("h_season_matches", np.nan) or 0), float(r.get("a_season_matches", np.nan) or 0))
        quality = 1.0 if (not np.isnan(played) and played >= 5) else 0.4
        out.extend(
            evaluate_match(
                match_id=mid, league=r["league"], home=r["home"], away=r["away"],
                kickoff=pd.Timestamp(r["date"]).isoformat(timespec="minutes"), p_model=p_final[i],
                prices=prices.get(mid, {}), policy=policy, p_sharp=p_sharp,
                components={k: v[i] for k, v in comps.items()}, data_quality=quality,
            )
        )
    return out


def select_by_day(candidates: list[BetCandidate], policy: StakingPolicy) -> list[BetCandidate]:
    by_day: dict[str, list[BetCandidate]] = {}
    for c in candidates:
        by_day.setdefault(c.kickoff[:10], []).append(c)
    chosen: list[BetCandidate] = []
    for day in sorted(by_day):
        chosen.extend(select_daily(by_day[day], policy))
    return chosen


def run_daily(
    s: Settings,
    now: datetime | None = None,
    notify: bool = False,
    events_override: dict[str, list[dict]] | None = None,
    history_override: pd.DataFrame | None = None,
    persist: bool = True,
) -> DailyResult:
    tz = ZoneInfo(s.timezone)
    now = now or datetime.now(tz)
    now_utc = now.astimezone(ZoneInfo("UTC"))
    warnings: list[str] = []

    history = history_override if history_override is not None else load_history(
        s.league_list, season_start_years(s.seasons_back), s.raw_dir, download_missing=True, refresh_current=True,
    )
    if history.empty:
        raise RuntimeError("Historique vide : vérifier l'accès réseau à football-data.co.uk ou lancer edgebet download")

    credits = None
    if events_override is not None:
        events = events_override
    else:
        events, credits = fetch_events(s, now_utc)
    n_events = sum(len(v) for v in events.values())

    fixtures, prices, sharp, snapshots, unmatched = build_fixtures(events, history, s)
    if unmatched:
        warnings.append(f"Équipes non reconnues : {', '.join(unmatched)}")

    run_id = None
    recs_out: list[dict] = []
    if fixtures.empty:
        msg = "Aucun match avec cotes dans l'horizon"
        if persist:
            with session_scope(s.db_url) as session:
                run = repo.start_run(session, "daily")
                repo.finish_run(session, run, "ok", msg, n_matches=0, n_recommendations=0, credits_remaining=credits)
                run_id = run.id
        return DailyResult(run_id, n_events, 0, 0, [], credits, unmatched, warnings, msg)

    bundle = load_bundle(s)
    cfg = feature_config_from_settings(s)
    rows, comps, p_final = predict_fixtures(history, fixtures, bundle, cfg)

    bankroll = s.bankroll
    if persist:
        with session_scope(s.db_url) as session:
            bankroll = repo.current_balance(session, s.bankroll)
    policy = policy_from_settings(s, bankroll)
    candidates = make_candidates(rows, comps, p_final, prices, sharp, policy, s.devig_method)
    chosen = select_by_day(candidates, policy)
    msg = f"{len(fixtures)} matchs, {len(candidates)} value bets candidats, {len(chosen)} retenus"
    log.info(msg)

    if persist:
        with session_scope(s.db_url) as session:
            run = repo.start_run(session, "daily")
            repo.save_odds_snapshots(session, run.id, snapshots)
            recs = repo.upsert_recommendations(session, run.id, chosen)
            repo.finish_run(session, run, "ok", msg, n_matches=len(fixtures), n_recommendations=len(recs), credits_remaining=credits)
            run_id = run.id
            recs_out = [rec_to_dict(r, s) for r in recs]
            if notify and recs:
                try:
                    from edgebet.notify.telegram import TelegramClient, send_grid

                    client = TelegramClient(s.telegram_bot_token)
                    ids = send_grid(client, s.telegram_chat_id, recs_out, now.date(), bankroll)
                    for r, mid in zip(recs, ids, strict=False):
                        r.telegram_message_id = mid
                except Exception as exc:
                    warnings.append(f"Notification Telegram impossible : {exc}")
                    log.warning("Telegram : %s", exc)
    else:
        recs_out = [c.to_dict() for c in chosen]

    return DailyResult(run_id, n_events, len(fixtures), len(candidates), recs_out, credits, unmatched, warnings, msg)
