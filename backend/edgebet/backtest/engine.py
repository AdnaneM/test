"""Backtest en marche avant (walk-forward) saison par saison.

Pour chaque saison de test S :
  * entraînement du GBM sur les saisons < S-1 ;
  * calibration (température) et poids du mélange ajustés sur la saison S-1 ;
  * ré-entraînement du GBM sur les saisons < S, puis prédiction de S ;
  * simulation de mise sur S avec les cotes choisies, règlement avec les résultats réels,
    CLV mesuré face aux cotes de clôture Pinnacle.
Aucune information postérieure au match n'est utilisée.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from edgebet.backtest.metrics import betting_summary, probability_metrics
from edgebet.betting.odds import devig_frame
from edgebet.betting.value import StakingPolicy, evaluate_match, select_daily
from edgebet.features.build import DC_COLS, FEATURES, FEATURES_NO_MARKET, MKT_COLS
from edgebet.models.calibration import apply_temperature, fit_temperature
from edgebet.models.ensemble import blend, fit_blend_weights
from edgebet.models.gbm import GBMModel
from edgebet.schema import OUTCOMES, odds_cols

log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    test_seasons: list[str] | None = None  # défaut : les 3 dernières saisons
    n_test_seasons: int = 3
    min_train_seasons: int = 3
    odds_book: str = "avg"  # cotes jouées : avg (réaliste), max (optimiste), b365, ps
    closing_book: str = "psc"
    sharp_book: str = "ps"
    use_market_features: bool = True
    components: list[str] = field(default_factory=lambda: ["gbm", "dc", "market"])
    policy: StakingPolicy = field(default_factory=StakingPolicy)
    devig_method: str = "power"
    flat_stake: float = 1.0


@dataclass
class BacktestResult:
    predictions: pd.DataFrame
    bets: pd.DataFrame
    metrics: dict
    weights: dict[str, dict[str, float]]
    temperatures: dict[str, float]
    config: BacktestConfig

    def summary_frame(self) -> pd.DataFrame:
        rows = []
        for scope, m in self.metrics["probability"].items():
            for model, vals in m.items():
                rows.append({"scope": scope, "model": model, **vals})
        return pd.DataFrame(rows)


def _probs(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return df[cols].to_numpy(dtype=float)


def run_backtest(features: pd.DataFrame, cfg: BacktestConfig | None = None) -> BacktestResult:
    cfg = cfg or BacktestConfig()
    df = features[features["y"].notna()].copy()
    seasons = sorted(df["season"].unique())
    test_seasons = cfg.test_seasons or seasons[-cfg.n_test_seasons :]
    feats = FEATURES if cfg.use_market_features else FEATURES_NO_MARKET
    preds: list[pd.DataFrame] = []
    weights: dict[str, dict[str, float]] = {}
    temperatures: dict[str, float] = {}

    for season in test_seasons:
        if season not in seasons:
            log.warning("Saison %s absente des données", season)
            continue
        i = seasons.index(season)
        if i - 1 < cfg.min_train_seasons:
            log.warning("Saison %s : pas assez d'historique (%d saisons), ignorée", season, i)
            continue
        val_season = seasons[i - 1]
        train_seasons = seasons[: i - 1]
        train = df[df["season"].isin(train_seasons) & df["dc_p_h"].notna()]
        val = df[(df["season"] == val_season) & df["dc_p_h"].notna()]
        test = df[df["season"] == season]
        if len(train) < 500 or len(val) < 100 or test.empty:
            log.warning("Saison %s : données insuffisantes (train=%d, val=%d)", season, len(train), len(val))
            continue

        gbm = GBMModel(feats).fit(train, train["y"].to_numpy(dtype=int))
        p_val = gbm.predict_proba(val)
        temp = fit_temperature(p_val, val["y"].to_numpy(dtype=int))
        comps_val = {"gbm": apply_temperature(p_val, temp), "dc": _probs(val, DC_COLS[:3]), "market": _probs(val, MKT_COLS)}
        w = fit_blend_weights(comps_val, val["y"].to_numpy(dtype=int), cfg.components)

        full_train = pd.concat([train, val])
        gbm_full = GBMModel(feats).fit(full_train, full_train["y"].to_numpy(dtype=int))
        p_gbm = apply_temperature(gbm_full.predict_proba(test), temp)
        comps = {"gbm": p_gbm, "dc": _probs(test, DC_COLS[:3]), "market": _probs(test, MKT_COLS)}
        p_final = blend(comps, w)

        rec = test[["match_id", "season", "league", "date", "home", "away", "hg", "ag", "result", "y"]].copy()
        for j, o in enumerate(OUTCOMES):
            rec[f"p_gbm_{o.lower()}"] = p_gbm[:, j]
            rec[f"p_dc_{o.lower()}"] = comps["dc"][:, j]
            rec[f"p_mkt_{o.lower()}"] = comps["market"][:, j]
            rec[f"p_final_{o.lower()}"] = p_final[:, j]
        for book in {cfg.odds_book, cfg.closing_book, cfg.sharp_book}:
            for c in odds_cols(book):
                rec[c] = test[c].to_numpy(dtype=float) if c in test.columns else np.nan
        close = devig_frame(rec, odds_cols(cfg.closing_book), cfg.devig_method)
        for j, o in enumerate(OUTCOMES):
            rec[f"p_close_{o.lower()}"] = close[:, j]
        preds.append(rec)
        weights[season] = w
        temperatures[season] = temp
        log.info("Saison %s : température %.2f, poids %s", season, temp, {k: round(v, 2) for k, v in w.items()})

    if not preds:
        raise RuntimeError("Backtest impossible : aucune saison testable (historique trop court ?)")
    predictions = pd.concat(preds, ignore_index=True)
    bets = simulate_bets(predictions, cfg)
    metrics = compute_metrics(predictions, bets)
    return BacktestResult(predictions, bets, metrics, weights, temperatures, cfg)


def simulate_bets(pred: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Applique la politique de mise jour par jour sur les prédictions et règle les paris."""
    policy = cfg.policy
    book_cols = odds_cols(cfg.odds_book)
    sharp_cols = odds_cols(cfg.sharp_book)
    p_sharp_all = devig_frame(pred, sharp_cols, cfg.devig_method)
    rows: list[dict] = []
    pred = pred.reset_index(drop=True)
    day = pred["date"].dt.normalize()
    for d in day.unique():
        idx = np.flatnonzero((day == d).to_numpy())
        candidates = []
        for i in idx:
            r = pred.iloc[i]
            p_model = np.array([r["p_final_h"], r["p_final_d"], r["p_final_a"]], dtype=float)
            if np.isnan(p_model).any():
                continue
            odds = np.array([r[c] for c in book_cols], dtype=float)
            if np.isnan(odds).any():
                continue
            comps = {
                "gbm": np.array([r["p_gbm_h"], r["p_gbm_d"], r["p_gbm_a"]], dtype=float),
                "dc": np.array([r["p_dc_h"], r["p_dc_d"], r["p_dc_a"]], dtype=float),
                "market": np.array([r["p_mkt_h"], r["p_mkt_d"], r["p_mkt_a"]], dtype=float),
            }
            cands = evaluate_match(
                match_id=r["match_id"], league=r["league"], home=r["home"], away=r["away"],
                kickoff=str(r["date"]), p_model=p_model, prices={cfg.odds_book: odds}, policy=policy,
                p_sharp=p_sharp_all[i], components=comps,
            )
            for c in cands:
                c.components["_row"] = i
            candidates.extend(cands)
        for c in select_daily(candidates, policy):
            i = int(c.components.pop("_row"))
            r = pred.iloc[i]
            j = OUTCOMES.index(c.selection)
            won = r["result"] == c.selection
            p_close = r[f"p_close_{c.selection.lower()}"]
            rows.append(
                {
                    "date": r["date"], "season": r["season"], "league": r["league"], "match_id": r["match_id"],
                    "home": r["home"], "away": r["away"], "selection": c.selection, "odds": c.odds,
                    "p_model": c.p_model, "p_sharp": c.p_sharp, "edge": c.edge, "edge_vs_sharp": c.edge_vs_sharp,
                    "risk": c.risk, "kelly": c.kelly, "stake": c.stake, "won": bool(won),
                    "pnl": c.stake * (c.odds - 1.0) if won else -c.stake,
                    "stake_flat": cfg.flat_stake,
                    "pnl_flat": cfg.flat_stake * (c.odds - 1.0) if won else -cfg.flat_stake,
                    "closing_odds": float(r[odds_cols(cfg.closing_book)[j]]),
                    "clv": (c.odds * p_close - 1.0) if not np.isnan(p_close) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def compute_metrics(pred: pd.DataFrame, bets: pd.DataFrame) -> dict:
    y = pred["y"].to_numpy(dtype=float)
    models = {
        "final": [f"p_final_{o.lower()}" for o in OUTCOMES],
        "gbm": [f"p_gbm_{o.lower()}" for o in OUTCOMES],
        "dixon_coles": [f"p_dc_{o.lower()}" for o in OUTCOMES],
        "market_open": [f"p_mkt_{o.lower()}" for o in OUTCOMES],
        "market_close": [f"p_close_{o.lower()}" for o in OUTCOMES],
    }
    prob: dict[str, dict[str, dict]] = {"all": {}}
    for name, cols in models.items():
        prob["all"][name] = probability_metrics(pred[cols].to_numpy(dtype=float), y)
    prob["all"]["uniform"] = {"n": int(len(y)), "log_loss": float(np.log(3)), "brier": 2 / 3, "accuracy": 1 / 3}
    for scope_col in ("season", "league"):
        for val, sub in pred.groupby(scope_col):
            key = f"{scope_col}={val}"
            prob[key] = {name: probability_metrics(sub[cols].to_numpy(dtype=float), sub["y"].to_numpy(dtype=float)) for name, cols in models.items()}

    betting: dict[str, dict] = {"all": betting_summary(bets), "all_flat": betting_summary(bets, "stake_flat", "pnl_flat")}
    if not bets.empty:
        for scope_col in ("season", "league", "risk"):
            for val, sub in bets.groupby(scope_col):
                betting[f"{scope_col}={val}"] = betting_summary(sub)
    return {"probability": prob, "betting": betting, "n_matches": int(len(pred)), "n_bets": int(len(bets))}
