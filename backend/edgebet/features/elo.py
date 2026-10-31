"""Classement Elo causal (mis à jour match après match) avec avantage du terrain et marge de victoire."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class EloConfig:
    k: float = 20.0
    hfa: float = 65.0  # avantage du terrain en points Elo
    init: float = 1500.0
    promoted_penalty: float = 100.0  # un nouvel entrant démarre sous la moyenne de la ligue
    min_known_for_penalty: int = 8
    mov: bool = True  # multiplicateur de marge de victoire (type FiveThirtyEight)


def mov_multiplier(goal_diff: int) -> float:
    gd = abs(int(goal_diff))
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return 1.75 + (gd - 3) / 8.0


def expected_home(rating_home: float, rating_away: float, hfa: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(rating_home + hfa - rating_away) / 400.0))


@dataclass
class EloRatings:
    cfg: EloConfig = field(default_factory=EloConfig)
    ratings: dict[str, float] = field(default_factory=dict)
    league_members: dict[str, set[str]] = field(default_factory=dict)

    def rating(self, team: str, league: str) -> float:
        if team in self.ratings:
            return self.ratings[team]
        members = self.league_members.setdefault(league, set())
        known = [self.ratings[t] for t in members if t in self.ratings]
        if len(known) >= self.cfg.min_known_for_penalty:
            start = float(np.mean(known)) - self.cfg.promoted_penalty
        else:
            start = self.cfg.init
        self.ratings[team] = start
        return start

    def update(self, home: str, away: str, league: str, hg: int, ag: int) -> None:
        rh, ra = self.rating(home, league), self.rating(away, league)
        self.league_members.setdefault(league, set()).update({home, away})
        exp_h = expected_home(rh, ra, self.cfg.hfa)
        score_h = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        mult = mov_multiplier(hg - ag) if self.cfg.mov else 1.0
        delta = self.cfg.k * mult * (score_h - exp_h)
        self.ratings[home] = rh + delta
        self.ratings[away] = ra - delta


def compute_elo_features(df: pd.DataFrame, cfg: EloConfig | None = None, ratings: EloRatings | None = None) -> pd.DataFrame:
    """Ajoute ``elo_h, elo_a, elo_diff, elo_exp_h`` (valeurs d'avant-match) ; met à jour après chaque match joué.

    ``df`` doit être trié par date. Les lignes sans résultat (matchs à venir) reçoivent les
    cotes Elo courantes sans mise à jour.
    """
    cfg = cfg or EloConfig()
    elo = ratings or EloRatings(cfg=cfg)
    n = len(df)
    elo_h = np.empty(n)
    elo_a = np.empty(n)
    hg_arr = df["hg"].to_numpy(dtype=float, na_value=np.nan)
    ag_arr = df["ag"].to_numpy(dtype=float, na_value=np.nan)
    homes = df["home"].to_numpy()
    aways = df["away"].to_numpy()
    leagues = df["league"].to_numpy()
    for i in range(n):
        h, a, lg = homes[i], aways[i], leagues[i]
        elo_h[i] = elo.rating(h, lg)
        elo_a[i] = elo.rating(a, lg)
        elo.league_members.setdefault(lg, set()).update({h, a})
        if not (np.isnan(hg_arr[i]) or np.isnan(ag_arr[i])):
            elo.update(h, a, lg, int(hg_arr[i]), int(ag_arr[i]))
    out = df.copy()
    out["elo_h"] = elo_h
    out["elo_a"] = elo_a
    out["elo_diff"] = elo_h + cfg.hfa - elo_a
    out["elo_exp_h"] = 1.0 / (1.0 + 10.0 ** (-out["elo_diff"] / 400.0))
    return out
