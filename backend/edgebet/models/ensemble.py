"""Combinaison de plusieurs sources de probabilités (pool linéaire pondéré)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from edgebet.models.calibration import log_loss


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max())
    return e / e.sum()


def blend(components: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    """Moyenne pondérée des probabilités ; les composantes manquantes (NaN) sont ignorées ligne par ligne."""
    names = [k for k in weights if k in components]
    if not names:
        raise ValueError("Aucune composante disponible pour le mélange")
    n = len(next(iter(components.values())))
    k = next(iter(components.values())).shape[1]
    num = np.zeros((n, k))
    den = np.zeros((n, 1))
    for name in names:
        p = np.asarray(components[name], dtype=float)
        ok = ~np.isnan(p).any(axis=1, keepdims=True)
        w = float(weights[name])
        num += np.where(ok, p, 0.0) * w
        den += ok * w
    out = np.full((n, k), np.nan)
    good = den[:, 0] > 0
    out[good] = num[good] / den[good]
    out[good] = out[good] / out[good].sum(axis=1, keepdims=True)
    return out


def fit_blend_weights(components: dict[str, np.ndarray], y: np.ndarray, names: list[str] | None = None) -> dict[str, float]:
    """Poids (somme 1) minimisant la log-loss sur un jeu de validation."""
    names = names or list(components)
    present = [n for n in names if n in components]
    if len(present) == 1:
        return {present[0]: 1.0}
    rows = np.ones(len(y), dtype=bool)
    for n in present:
        rows &= ~np.isnan(components[n]).any(axis=1)
    if rows.sum() < 50:
        return {n: 1.0 / len(present) for n in present}
    comps = {n: components[n][rows] for n in present}
    yy = y[rows]

    def objective(z: np.ndarray) -> float:
        w = dict(zip(present, _softmax(z), strict=True))
        return log_loss(blend(comps, w), yy)

    res = minimize(objective, np.zeros(len(present)), method="Nelder-Mead", options={"maxiter": 2000, "xatol": 1e-4, "fatol": 1e-7})
    return {n: float(w) for n, w in zip(present, _softmax(res.x), strict=True)}
