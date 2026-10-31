"""Métriques de qualité probabiliste et de performance de mise."""

from __future__ import annotations

import numpy as np
import pandas as pd

from edgebet.models.calibration import brier_multiclass, log_loss


def probability_metrics(probs: np.ndarray, y: np.ndarray) -> dict[str, float]:
    mask = ~np.isnan(probs).any(axis=1) & ~np.isnan(y)
    if mask.sum() == 0:
        return {"n": 0, "log_loss": float("nan"), "brier": float("nan"), "accuracy": float("nan")}
    p, yy = probs[mask], y[mask].astype(int)
    return {
        "n": int(mask.sum()),
        "log_loss": log_loss(p, yy),
        "brier": brier_multiclass(p, yy),
        "accuracy": float(np.mean(p.argmax(axis=1) == yy)),
    }


def max_drawdown(cum_profit: np.ndarray) -> float:
    if len(cum_profit) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum_profit]))
    dd = np.concatenate([[0.0], cum_profit]) - peak
    return float(dd.min())


def betting_summary(bets: pd.DataFrame, stake_col: str = "stake", pnl_col: str = "pnl") -> dict[str, float]:
    if bets is None or bets.empty:
        return {"n_bets": 0, "staked": 0.0, "pnl": 0.0, "roi": float("nan"), "hit_rate": float("nan"),
                "avg_odds": float("nan"), "max_drawdown": 0.0, "clv_mean": float("nan"), "edge_mean": float("nan")}
    b = bets.sort_values("date")
    staked = float(b[stake_col].sum())
    pnl = float(b[pnl_col].sum())
    return {
        "n_bets": int(len(b)),
        "staked": staked,
        "pnl": pnl,
        "roi": pnl / staked if staked > 0 else float("nan"),
        "hit_rate": float(b["won"].mean()),
        "avg_odds": float(b["odds"].mean()),
        "max_drawdown": max_drawdown(b[pnl_col].cumsum().to_numpy()),
        "clv_mean": float(b["clv"].mean()) if "clv" in b and b["clv"].notna().any() else float("nan"),
        "edge_mean": float(b["edge"].mean()),
    }
