"""Outils de cotes : probabilités implicites, retrait de la marge (de-vig), cotes justes."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

DevigMethod = Literal["multiplicative", "power", "shin"]


def implied(odds) -> np.ndarray:
    o = np.asarray(odds, dtype=float)
    return 1.0 / o


def overround(odds) -> float:
    return float(np.nansum(implied(odds)) - 1.0)


def _devig_power(pi: np.ndarray) -> np.ndarray:
    lo, hi = 1.0, 5.0
    for _ in range(80):
        k = 0.5 * (lo + hi)
        s = np.sum(pi**k)
        if s > 1.0:
            lo = k
        else:
            hi = k
    k = 0.5 * (lo + hi)
    p = pi**k
    return p / p.sum()


def _devig_shin(pi: np.ndarray) -> np.ndarray:
    total = pi.sum()
    if total <= 1.0:
        return pi / total

    def probs(z: float) -> np.ndarray:
        return (np.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / total) - z) / (2.0 * (1.0 - z))

    lo, hi = 0.0, 0.5
    for _ in range(80):
        z = 0.5 * (lo + hi)
        if probs(z).sum() > 1.0:
            lo = z
        else:
            hi = z
    p = probs(0.5 * (lo + hi))
    return p / p.sum()


def devig(odds, method: DevigMethod = "power") -> np.ndarray:
    """Probabilités justes à partir des cotes d'un même marché (retrait de la marge)."""
    pi = implied(odds)
    if np.isnan(pi).any() or (pi <= 0).any():
        return np.full_like(pi, np.nan)
    if method == "multiplicative":
        return pi / pi.sum()
    if method == "power":
        return _devig_power(pi)
    if method == "shin":
        return _devig_shin(pi)
    raise ValueError(f"Méthode de de-vig inconnue : {method}")


def devig_frame(df: pd.DataFrame, cols: list[str], method: DevigMethod = "power") -> np.ndarray:
    """De-vig ligne par ligne d'un DataFrame (colonnes de cotes d'un même marché)."""
    arr = df[cols].to_numpy(dtype=float)
    out = np.full_like(arr, np.nan)
    ok = ~np.isnan(arr).any(axis=1) & (arr > 1.0).all(axis=1)
    if method == "multiplicative":
        pi = 1.0 / arr[ok]
        out[ok] = pi / pi.sum(axis=1, keepdims=True)
        return out
    for i in np.flatnonzero(ok):
        out[i] = devig(arr[i], method)
    return out


def fair_odds(prob: float) -> float:
    return float("inf") if prob <= 0 else 1.0 / prob


def best_price(prices: dict[str, float]) -> tuple[str | None, float]:
    """Meilleure cote parmi plusieurs bookmakers : (bookmaker, cote)."""
    best_book, best = None, float("nan")
    for book, price in prices.items():
        if price is None or np.isnan(price):
            continue
        if np.isnan(best) or price > best:
            best_book, best = book, float(price)
    return best_book, best
