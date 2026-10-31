"""Modèle de Dixon & Coles (1997) : Poisson bivarié corrigé pour les scores faibles,
avec pondération temporelle exponentielle. Gradient analytique pour un ajustement rapide."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson


@dataclass
class DCParams:
    teams: list[str]
    attack: np.ndarray
    defense: np.ndarray
    home_adv: float
    rho: float
    n_matches: int = 0
    ref_date: pd.Timestamp | None = None

    def index(self) -> dict[str, int]:
        return {t: i for i, t in enumerate(self.teams)}

    def team_strength(self, team: str, penalty: float = 0.1) -> tuple[float, float]:
        """(attaque, défense) ; équipe inconnue => moyenne de la ligue légèrement pénalisée."""
        idx = self.index().get(team)
        if idx is None:
            return float(self.attack.mean() - penalty), float(self.defense.mean() + penalty)
        return float(self.attack[idx]), float(self.defense[idx])

    def rates(self, home: str, away: str) -> tuple[float, float]:
        ah, dh = self.team_strength(home)
        aa, da = self.team_strength(away)
        lam = float(np.exp(ah + da + self.home_adv))
        mu = float(np.exp(aa + dh))
        return lam, mu

    def to_dict(self) -> dict:
        return {
            "teams": list(self.teams),
            "attack": self.attack.tolist(),
            "defense": self.defense.tolist(),
            "home_adv": self.home_adv,
            "rho": self.rho,
            "n_matches": self.n_matches,
            "ref_date": None if self.ref_date is None else str(self.ref_date),
        }


def _unpack(theta: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray, float, float]:
    attack_free = theta[: n - 1]
    attack = np.concatenate([attack_free, [-attack_free.sum()]])
    defense = theta[n - 1 : 2 * n - 1]
    gamma = theta[2 * n - 1]
    rho = theta[2 * n]
    return attack, defense, float(gamma), float(rho)


def _nll_and_grad(theta: np.ndarray, hi: np.ndarray, ai: np.ndarray, x: np.ndarray, y: np.ndarray, w: np.ndarray, n: int):
    attack, defense, gamma, rho = _unpack(theta, n)
    lam = np.exp(attack[hi] + defense[ai] + gamma)
    mu = np.exp(attack[ai] + defense[hi])

    tau = np.ones_like(lam)
    dt_dlam = np.zeros_like(lam)
    dt_dmu = np.zeros_like(lam)
    dt_drho = np.zeros_like(lam)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    tau[m00] = 1.0 - lam[m00] * mu[m00] * rho
    dt_dlam[m00] = -mu[m00] * rho
    dt_dmu[m00] = -lam[m00] * rho
    dt_drho[m00] = -lam[m00] * mu[m00]
    tau[m01] = 1.0 + lam[m01] * rho
    dt_dlam[m01] = rho
    dt_drho[m01] = lam[m01]
    tau[m10] = 1.0 + mu[m10] * rho
    dt_dmu[m10] = rho
    dt_drho[m10] = mu[m10]
    tau[m11] = 1.0 - rho
    dt_drho[m11] = -1.0
    tau = np.maximum(tau, 1e-9)

    ll = w * (np.log(tau) + x * np.log(lam) - lam + y * np.log(mu) - mu)
    dlam = w * ((x - lam) + dt_dlam / tau * lam)  # dérivée par rapport à log(lam)
    dmu = w * ((y - mu) + dt_dmu / tau * mu)
    drho = w * dt_drho / tau

    g_attack = np.bincount(hi, dlam, minlength=n) + np.bincount(ai, dmu, minlength=n)
    g_defense = np.bincount(ai, dlam, minlength=n) + np.bincount(hi, dmu, minlength=n)
    g_gamma = dlam.sum()
    g_rho = drho.sum()
    g_attack_free = g_attack[: n - 1] - g_attack[n - 1]
    grad = np.concatenate([g_attack_free, g_defense, [g_gamma, g_rho]])
    return -ll.sum(), -grad


def fit_dixon_coles(
    matches: pd.DataFrame,
    xi: float = 0.002,
    ref_date: pd.Timestamp | None = None,
    init: DCParams | None = None,
    max_iter: int = 300,
) -> DCParams:
    """Ajuste le modèle sur des matchs joués (colonnes ``date, home, away, hg, ag``).

    ``xi`` : décroissance exponentielle par jour (0 = pas de pondération).
    ``init`` : paramètres précédents pour un démarrage à chaud.
    """
    df = matches.dropna(subset=["hg", "ag"])
    if df.empty:
        raise ValueError("Aucun match joué pour ajuster Dixon-Coles")
    ref_date = pd.Timestamp(ref_date) if ref_date is not None else pd.Timestamp(df["date"].max())
    teams = sorted(set(df["home"]) | set(df["away"]))
    n = len(teams)
    idx = {t: i for i, t in enumerate(teams)}
    hi = df["home"].map(idx).to_numpy(dtype=int)
    ai = df["away"].map(idx).to_numpy(dtype=int)
    x = df["hg"].to_numpy(dtype=float)
    y = df["ag"].to_numpy(dtype=float)
    days = (ref_date - pd.to_datetime(df["date"])).dt.total_seconds().to_numpy() / 86400.0
    w = np.exp(-xi * np.maximum(days, 0.0)) if xi > 0 else np.ones_like(days)

    theta0 = np.zeros(2 * n + 1)
    theta0[2 * n - 1] = 0.25
    theta0[2 * n] = -0.05
    if init is not None:
        prev = init.index()
        att = np.array([init.attack[prev[t]] if t in prev else 0.0 for t in teams])
        att -= att.mean()
        theta0[: n - 1] = att[: n - 1]
        theta0[n - 1 : 2 * n - 1] = np.array([init.defense[prev[t]] if t in prev else init.defense.mean() for t in teams])
        theta0[2 * n - 1] = init.home_adv
        theta0[2 * n] = init.rho

    bounds = [(-3.0, 3.0)] * (2 * n - 1) + [(-1.0, 1.5), (-0.5, 0.5)]
    res = minimize(
        _nll_and_grad,
        theta0,
        args=(hi, ai, x, y, w, n),
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": max_iter},
    )
    attack, defense, gamma, rho = _unpack(res.x, n)
    return DCParams(teams=teams, attack=attack, defense=defense, home_adv=gamma, rho=rho, n_matches=len(df), ref_date=ref_date)


def score_matrix(lam: float, mu: float, rho: float, max_goals: int = 10) -> np.ndarray:
    goals = np.arange(max_goals + 1)
    ph = poisson.pmf(goals, lam)
    pa = poisson.pmf(goals, mu)
    m = np.outer(ph, pa)
    m[0, 0] *= 1.0 - lam * mu * rho
    m[0, 1] *= 1.0 + lam * rho
    m[1, 0] *= 1.0 + mu * rho
    m[1, 1] *= 1.0 - rho
    m = np.maximum(m, 0.0)
    s = m.sum()
    return m / s if s > 0 else m


def outcome_probs(m: np.ndarray) -> dict[str, float]:
    home = float(np.tril(m, -1).sum())
    draw = float(np.trace(m))
    away = float(np.triu(m, 1).sum())
    goals = np.add.outer(np.arange(m.shape[0]), np.arange(m.shape[1]))
    over25 = float(m[goals > 2.5].sum())
    btts = float(m[1:, 1:].sum())
    return {"p_h": home, "p_d": draw, "p_a": away, "p_over25": over25, "p_under25": 1.0 - over25, "p_btts": btts}


def predict_match(params: DCParams, home: str, away: str, max_goals: int = 10) -> dict[str, float]:
    lam, mu = params.rates(home, away)
    out = outcome_probs(score_matrix(lam, mu, params.rho, max_goals))
    out["lambda_h"] = lam
    out["mu_a"] = mu
    return out
