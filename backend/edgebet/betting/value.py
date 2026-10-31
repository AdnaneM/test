"""Détection de value bets, mise de Kelly fractionnée et score de risque."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from edgebet.schema import OUTCOME_LABELS_FR, OUTCOMES


@dataclass
class StakingPolicy:
    bankroll: float = 100.0
    kelly_fraction: float = 0.25
    max_stake_fraction: float = 0.05
    min_edge: float = 0.03
    min_odds: float = 1.3
    max_odds: float = 6.0
    min_probability: float = 0.12
    require_sharp_agreement: bool = True
    sharp_tolerance: float = 0.02
    max_bets_per_day: int = 6
    round_to: float = 0.5


@dataclass
class BetCandidate:
    match_id: str
    league: str
    home: str
    away: str
    kickoff: str
    market: str
    selection: str
    selection_label: str
    p_model: float
    odds: float
    bookmaker: str
    edge: float
    kelly: float
    stake: float
    risk: int
    p_sharp: float | None = None
    fair_odds_sharp: float | None = None
    edge_vs_sharp: float | None = None
    disagreement: float | None = None
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def kelly_fraction(p: float, odds: float) -> float:
    if odds <= 1.0 or p <= 0.0:
        return 0.0
    return max(0.0, (p * odds - 1.0) / (odds - 1.0))


def round_stake(stake: float, step: float) -> float:
    if step <= 0:
        return round(stake, 2)
    return float(np.floor(stake / step + 1e-9) * step)


def risk_score(odds: float, disagreement: float | None = None, data_quality: float = 1.0) -> int:
    """Score 1 (sûr) à 5 (spéculatif) : niveau de cote, désaccord entre modèles, qualité des données."""
    if odds < 1.6:
        base = 1
    elif odds < 2.2:
        base = 2
    elif odds < 3.2:
        base = 3
    elif odds < 5.0:
        base = 4
    else:
        base = 5
    if disagreement is not None and disagreement > 0.08:
        base += 1
    if data_quality < 0.5:
        base += 1
    return int(min(5, max(1, base)))


def evaluate_match(
    *,
    match_id: str,
    league: str,
    home: str,
    away: str,
    kickoff: str,
    p_model: np.ndarray,
    prices: dict[str, np.ndarray],
    policy: StakingPolicy,
    p_sharp: np.ndarray | None = None,
    components: dict[str, np.ndarray] | None = None,
    data_quality: float = 1.0,
    market: str = "1X2",
) -> list[BetCandidate]:
    """Évalue les trois issues d'un match 1N2 face aux cotes de plusieurs bookmakers.

    ``prices`` : {bookmaker: array([cote_H, cote_N, cote_A])}.
    Retourne les candidats qui passent les filtres de la politique (au plus un par issue).
    """
    out: list[BetCandidate] = []
    comps = components or {}
    comp_stack = np.array([v for v in comps.values()]) if comps else None
    for j, sel in enumerate(OUTCOMES):
        p = float(p_model[j])
        if np.isnan(p) or p < policy.min_probability:
            continue
        best_book, best_odds = None, 0.0
        for book, arr in prices.items():
            o = float(arr[j]) if arr is not None else float("nan")
            if np.isnan(o):
                continue
            if o > best_odds:
                best_book, best_odds = book, o
        if best_book is None or best_odds < policy.min_odds or best_odds > policy.max_odds:
            continue
        edge = p * best_odds - 1.0
        if edge < policy.min_edge:
            continue
        ps = None if p_sharp is None or np.isnan(p_sharp[j]) else float(p_sharp[j])
        edge_sharp = None if ps is None else ps * best_odds - 1.0
        if policy.require_sharp_agreement and edge_sharp is not None and edge_sharp < -policy.sharp_tolerance:
            continue
        disagreement = None if comp_stack is None else float(np.nanstd(comp_stack[:, j]))
        k = kelly_fraction(p, best_odds)
        stake = min(k * policy.kelly_fraction, policy.max_stake_fraction) * policy.bankroll
        stake = round_stake(stake, policy.round_to)
        if stake <= 0:
            continue
        out.append(
            BetCandidate(
                match_id=match_id,
                league=league,
                home=home,
                away=away,
                kickoff=kickoff,
                market=market,
                selection=sel,
                selection_label=OUTCOME_LABELS_FR[sel],
                p_model=round(p, 4),
                odds=best_odds,
                bookmaker=best_book,
                edge=round(edge, 4),
                kelly=round(k, 4),
                stake=stake,
                risk=risk_score(best_odds, disagreement, data_quality),
                p_sharp=None if ps is None else round(ps, 4),
                fair_odds_sharp=None if ps is None or ps <= 0 else round(1.0 / ps, 3),
                edge_vs_sharp=None if edge_sharp is None else round(edge_sharp, 4),
                disagreement=None if disagreement is None else round(disagreement, 4),
                components={k_: round(float(v[j]), 4) for k_, v in comps.items()},
            )
        )
    return out


def select_daily(candidates: list[BetCandidate], policy: StakingPolicy, one_per_match: bool = True) -> list[BetCandidate]:
    """Classe par edge décroissante, un pari par match au plus, plafonne le nombre quotidien."""
    ranked = sorted(candidates, key=lambda c: (c.edge, c.p_model), reverse=True)
    chosen: list[BetCandidate] = []
    seen: set[str] = set()
    for c in ranked:
        if one_per_match and c.match_id in seen:
            continue
        chosen.append(c)
        seen.add(c.match_id)
        if len(chosen) >= policy.max_bets_per_day:
            break
    return chosen
