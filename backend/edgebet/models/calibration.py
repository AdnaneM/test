"""Calibration des probabilités (temperature scaling) et diagnostics de calibration."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar


def log_loss(probs: np.ndarray, y: np.ndarray, eps: float = 1e-12) -> float:
    p = np.clip(probs[np.arange(len(y)), y], eps, 1.0)
    return float(-np.mean(np.log(p)))


def brier_multiclass(probs: np.ndarray, y: np.ndarray) -> float:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def apply_temperature(probs: np.ndarray, temperature: float, eps: float = 1e-12) -> np.ndarray:
    logits = np.log(np.clip(probs, eps, 1.0)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(probs: np.ndarray, y: np.ndarray) -> float:
    """Température minimisant la log-loss (T>1 adoucit, T<1 accentue)."""
    mask = ~np.isnan(probs).any(axis=1)
    if mask.sum() < 50:
        return 1.0
    p, yy = probs[mask], y[mask]
    res = minimize_scalar(lambda t: log_loss(apply_temperature(p, t), yy), bounds=(0.3, 5.0), method="bounded")
    return float(res.x)


def calibration_table(prob: np.ndarray, hit: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """Pour une probabilité prédite d'un événement binaire : fréquence observée par tranche."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(prob, edges) - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        rows.append(
            {
                "bin_low": edges[b],
                "bin_high": edges[b + 1],
                "n": int(m.sum()),
                "p_mean": float(prob[m].mean()),
                "observed": float(hit[m].mean()),
            }
        )
    return pd.DataFrame(rows)


def expected_calibration_error(prob: np.ndarray, hit: np.ndarray, bins: int = 10) -> float:
    t = calibration_table(prob, hit, bins)
    if t.empty:
        return float("nan")
    return float(np.sum(t["n"] / t["n"].sum() * np.abs(t["p_mean"] - t["observed"])))
