"""Entraînement du modèle de production sur tout l'historique disponible.

Protocole : GBM entraîné sur toutes les saisons sauf la dernière complète ; température et poids du
mélange ajustés sur cette dernière saison ; puis GBM ré-entraîné sur tout pour la production.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from edgebet.backtest.metrics import probability_metrics
from edgebet.features.build import DC_COLS, FEATURES, FEATURES_NO_MARKET, MKT_COLS, FeatureConfig
from edgebet.models.bundle import ModelBundle
from edgebet.models.calibration import apply_temperature, fit_temperature
from edgebet.models.ensemble import blend, fit_blend_weights
from edgebet.models.gbm import GBMModel

log = logging.getLogger(__name__)


def train_bundle(
    features: pd.DataFrame,
    feature_cfg: FeatureConfig,
    use_market_features: bool = True,
    components: list[str] | None = None,
    min_matches_in_season: int = 150,
) -> ModelBundle:
    components = components or ["gbm", "dc", "market"]
    df = features[features["y"].notna() & features["dc_p_h"].notna()].copy()
    if df.empty:
        raise RuntimeError("Aucune ligne exploitable pour l'entraînement (features Dixon-Coles absentes ?)")
    counts = df.groupby("season").size()
    complete = [s for s, n in counts.items() if n >= min_matches_in_season]
    seasons = sorted(complete)
    if len(seasons) < 3:
        raise RuntimeError(f"Historique trop court pour entraîner ({len(seasons)} saisons complètes)")
    val_season = seasons[-1]
    feats = FEATURES if use_market_features else FEATURES_NO_MARKET
    train = df[df["season"].isin(seasons[:-1])]
    val = df[df["season"] == val_season]
    y_tr = train["y"].to_numpy(dtype=int)
    y_val = val["y"].to_numpy(dtype=int)

    gbm = GBMModel(feats).fit(train, y_tr)
    p_val = gbm.predict_proba(val)
    temp = fit_temperature(p_val, y_val)
    comps_val = {
        "gbm": apply_temperature(p_val, temp),
        "dc": val[DC_COLS[:3]].to_numpy(dtype=float),
        "market": val[MKT_COLS].to_numpy(dtype=float),
    }
    weights = fit_blend_weights(comps_val, y_val, components)
    p_blend_val = blend(comps_val, weights)
    metrics = {
        "validation_season": val_season,
        "gbm": probability_metrics(comps_val["gbm"], y_val.astype(float)),
        "dixon_coles": probability_metrics(comps_val["dc"], y_val.astype(float)),
        "market": probability_metrics(comps_val["market"], y_val.astype(float)),
        "blend": probability_metrics(p_blend_val, y_val.astype(float)),
        "uniform_log_loss": float(np.log(3)),
    }
    log.info("Validation %s : %s", val_season, {k: round(v["log_loss"], 4) for k, v in metrics.items() if isinstance(v, dict)})

    all_df = df[df["season"].isin(seasons)]
    gbm_full = GBMModel(feats).fit(all_df, all_df["y"].to_numpy(dtype=int))
    return ModelBundle(
        gbm=gbm_full, features=feats, temperature=temp, weights=weights,
        feature_config=feature_cfg.to_dict(), seasons=seasons, metrics=metrics,
    )
