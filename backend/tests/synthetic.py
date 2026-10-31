"""Génération de données synthétiques pour les tests : une ligue simulée par un processus Dixon-Coles
connu, avec des cotes bruitées et margées comme celles d'un bookmaker. Aucune donnée réelle."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from edgebet.models.dixon_coles import outcome_probs, score_matrix
from edgebet.schema import make_match_id, result_from_goals


def _odds_from_probs(p: np.ndarray, margin: float, noise: float, rng: np.random.Generator) -> np.ndarray:
    q = p * np.exp(rng.normal(0.0, noise, size=p.shape))
    q = q / q.sum()
    return 1.0 / (q * (1.0 + margin))


def simulate_league(
    n_teams: int = 18,
    n_seasons: int = 5,
    start_year: int = 2018,
    league: str = "F1",
    seed: int = 0,
    home_adv: float = 0.28,
    rho: float = -0.08,
    attack_sd: float = 0.3,
    defense_sd: float = 0.2,
    drift: float = 0.05,
) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    teams = [f"Team {i:02d}" for i in range(n_teams)]
    attack = rng.normal(0.0, attack_sd, n_teams)
    attack -= attack.mean()
    defense = rng.normal(0.0, defense_sd, n_teams)
    rows = []
    truth = {"home_adv": home_adv, "rho": rho, "attack": {}, "defense": {}}
    for s in range(n_seasons):
        year = start_year + s
        attack = attack + rng.normal(0.0, drift, n_teams)
        attack -= attack.mean()
        defense = defense + rng.normal(0.0, drift, n_teams)
        truth["attack"][year] = dict(zip(teams, attack, strict=True))
        truth["defense"][year] = dict(zip(teams, defense, strict=True))
        # double round robin : calendrier circulaire
        order = list(range(n_teams))
        rounds = []
        for r in range(n_teams - 1):
            pairs = []
            for i in range(n_teams // 2):
                a, b = order[i], order[-1 - i]
                pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
            rounds.append(pairs)
            order = [order[0]] + [order[-1]] + order[1:-1]
        rounds = rounds + [[(b, a) for a, b in pairs] for pairs in rounds]
        day0 = datetime(year, 8, 10, 20, 0)
        for k, pairs in enumerate(rounds):
            d = day0 + timedelta(days=7 * k)
            for hi, ai in pairs:
                lam = float(np.exp(attack[hi] + defense[ai] + home_adv))
                mu = float(np.exp(attack[ai] + defense[hi]))
                m = score_matrix(lam, mu, rho, max_goals=8)
                flat = m.ravel() / m.sum()
                idx = rng.choice(len(flat), p=flat)
                hg, ag = divmod(int(idx), m.shape[1])
                p = outcome_probs(m)
                p_true = np.array([p["p_h"], p["p_d"], p["p_a"]])
                ps = _odds_from_probs(p_true, 0.03, 0.04, rng)
                psc = _odds_from_probs(p_true, 0.025, 0.015, rng)
                avg = _odds_from_probs(p_true, 0.06, 0.06, rng)
                b365 = _odds_from_probs(p_true, 0.05, 0.06, rng)
                shots_h = rng.poisson(9 + 4 * lam)
                shots_a = rng.poisson(9 + 4 * mu)
                rows.append(
                    {
                        "match_id": make_match_id(league, d, teams[hi], teams[ai]),
                        "sport": "football", "league": league, "season": f"{year}-{(year + 1) % 100:02d}", "date": d,
                        "home": teams[hi], "away": teams[ai], "hg": hg, "ag": ag, "result": result_from_goals(hg, ag),
                        "shots_h": shots_h, "shots_a": shots_a,
                        "sot_h": rng.binomial(shots_h, 0.35), "sot_a": rng.binomial(shots_a, 0.35),
                        "corners_h": rng.poisson(5), "corners_a": rng.poisson(5),
                        "odds_ps_h": ps[0], "odds_ps_d": ps[1], "odds_ps_a": ps[2],
                        "odds_psc_h": psc[0], "odds_psc_d": psc[1], "odds_psc_a": psc[2],
                        "odds_avg_h": avg[0], "odds_avg_d": avg[1], "odds_avg_a": avg[2],
                        "odds_max_h": avg[0] * 1.03, "odds_max_d": avg[1] * 1.03, "odds_max_a": avg[2] * 1.03,
                        "odds_b365_h": b365[0], "odds_b365_d": b365[1], "odds_b365_a": b365[2],
                        "p_true_h": p_true[0], "p_true_d": p_true[1], "p_true_a": p_true[2],
                    }
                )
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return df, truth
