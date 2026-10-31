"""Assemblage de la matrice de features. Toutes les features sont causales :
elles n'utilisent que l'information disponible avant le coup d'envoi."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from edgebet.betting.odds import devig_frame
from edgebet.features.elo import EloConfig, compute_elo_features
from edgebet.features.form import add_form_features
from edgebet.models.dixon_coles import DCParams, fit_dixon_coles, predict_match
from edgebet.models.gbm import league_code_series
from edgebet.schema import RESULT_CODES, odds_cols

log = logging.getLogger(__name__)


@dataclass
class FeatureConfig:
    dc_xi: float = 0.002
    dc_refit_days: int = 7
    dc_window_days: int = 1100
    dc_min_matches: int = 120
    devig_method: str = "power"
    market_book: str = "ps"  # cotes d'ouverture Pinnacle dans l'historique football-data
    elo: EloConfig = field(default_factory=EloConfig)

    def to_dict(self) -> dict:
        return {
            "dc_xi": self.dc_xi,
            "dc_refit_days": self.dc_refit_days,
            "dc_window_days": self.dc_window_days,
            "dc_min_matches": self.dc_min_matches,
            "devig_method": self.devig_method,
            "market_book": self.market_book,
            "elo_k": self.elo.k,
            "elo_hfa": self.elo.hfa,
        }


DC_COLS = ["dc_p_h", "dc_p_d", "dc_p_a", "dc_lambda_h", "dc_mu_a", "dc_p_over25"]
MKT_COLS = ["mkt_p_h", "mkt_p_d", "mkt_p_a"]

FORM_FEATURES = [
    "h_pts_5", "h_gf_5", "h_ga_5", "h_sotf_5", "h_sota_5",
    "h_pts_10", "h_gf_10", "h_ga_10", "h_sf_10", "h_sa_10", "h_sotf_10", "h_sota_10",
    "a_pts_5", "a_gf_5", "a_ga_5", "a_sotf_5", "a_sota_5",
    "a_pts_10", "a_gf_10", "a_ga_10", "a_sf_10", "a_sa_10", "a_sotf_10", "a_sota_10",
    "h_home_pts_5", "a_away_pts_5", "h_rest", "a_rest", "rest_diff",
    "h_season_matches", "a_season_matches", "pts_diff_5", "gd_diff_5", "pts_diff_10", "gd_diff_10",
]

FEATURES: list[str] = ["elo_diff", "elo_exp_h", "elo_h", "elo_a", *FORM_FEATURES, *DC_COLS, *MKT_COLS, "league_code"]
FEATURES_NO_MARKET: list[str] = [f for f in FEATURES if f not in MKT_COLS]


def add_market_features(df: pd.DataFrame, cfg: FeatureConfig) -> pd.DataFrame:
    """Probabilités implicites (sans marge) du bookmaker de référence.

    Historique : cotes d'ouverture Pinnacle (``odds_ps_*``). Pipeline quotidien : les colonnes
    ``odds_sharp_*`` (Pinnacle en direct) sont prioritaires quand elles existent.
    """
    out = df.copy()
    out[MKT_COLS] = np.nan
    cols = odds_cols(cfg.market_book)
    if all(c in out.columns for c in cols):
        out[MKT_COLS] = devig_frame(out, cols, cfg.devig_method)
    sharp = odds_cols("sharp")
    if all(c in out.columns for c in sharp):
        live = devig_frame(out, sharp, cfg.devig_method)
        ok = ~np.isnan(live).any(axis=1)
        if ok.any():
            out.loc[ok, MKT_COLS] = live[ok]
    return out


def add_dixon_coles_features(df: pd.DataFrame, cfg: FeatureConfig) -> tuple[pd.DataFrame, dict[str, DCParams]]:
    """Dixon-Coles en marche avant par ligue : réajusté tous les ``dc_refit_days`` jours
    sur une fenêtre glissante, prédictions pour les matchs du jour uniquement avec le passé."""
    out = df.copy()
    for c in DC_COLS:
        out[c] = np.nan
    last_params: dict[str, DCParams] = {}
    window = pd.Timedelta(days=cfg.dc_window_days)
    for league, idx in out.groupby("league", sort=False).groups.items():
        sub = out.loc[idx].sort_values("date")
        played = sub.dropna(subset=["hg", "ag"])
        day = sub["date"].dt.normalize()
        params: DCParams | None = None
        last_fit: pd.Timestamp | None = None
        rows_idx: list = []
        rows_val: list[list[float]] = []
        for d in day.unique():
            d = pd.Timestamp(d)
            if params is None or last_fit is None or (d - last_fit).days >= cfg.dc_refit_days:
                hist = played[(played["date"] < d) & (played["date"] >= d - window)]
                if len(hist) >= cfg.dc_min_matches:
                    try:
                        params = fit_dixon_coles(hist, xi=cfg.dc_xi, ref_date=d, init=params)
                        last_fit = d
                    except Exception as exc:  # pragma: no cover - robustesse
                        log.warning("Dixon-Coles %s %s : %s", league, d.date(), exc)
            if params is None:
                continue
            todays = sub[day == d]
            for i, r in todays.iterrows():
                pr = predict_match(params, r["home"], r["away"])
                rows_idx.append(i)
                rows_val.append([pr["p_h"], pr["p_d"], pr["p_a"], pr["lambda_h"], pr["mu_a"], pr["p_over25"]])
        if rows_idx:
            out.loc[rows_idx, DC_COLS] = np.array(rows_val)
        if params is not None:
            last_params[str(league)] = params
    return out, last_params


def build_feature_frame(df: pd.DataFrame, cfg: FeatureConfig | None = None) -> tuple[pd.DataFrame, dict[str, DCParams]]:
    """Pipeline complet de features. Retourne (DataFrame, derniers paramètres Dixon-Coles par ligue)."""
    cfg = cfg or FeatureConfig()
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["date", "league", "match_id"]).reset_index(drop=True)
    out = compute_elo_features(out, cfg.elo)
    out = add_form_features(out)
    out = add_market_features(out, cfg)
    out, dc_params = add_dixon_coles_features(out, cfg)
    out["league_code"] = league_code_series(out)
    out["y"] = out["result"].map(RESULT_CODES).astype(float)
    return out, dc_params
