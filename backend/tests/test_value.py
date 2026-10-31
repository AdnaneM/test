import numpy as np

from edgebet.betting.value import StakingPolicy, evaluate_match, kelly_fraction, risk_score, select_daily


def test_kelly_formula():
    assert abs(kelly_fraction(0.5, 2.5) - (0.5 * 2.5 - 1) / 1.5) < 1e-12
    assert kelly_fraction(0.3, 2.0) == 0.0
    assert kelly_fraction(0.5, 1.0) == 0.0


def test_risk_score_bounds():
    assert risk_score(1.3) == 1
    assert risk_score(8.0) == 5
    assert risk_score(2.0, disagreement=0.2) == 3
    assert 1 <= risk_score(3.0, disagreement=0.5, data_quality=0.1) <= 5


def test_evaluate_match_filters_and_stakes():
    policy = StakingPolicy(bankroll=100, kelly_fraction=0.25, max_stake_fraction=0.05, min_edge=0.03, round_to=0.5)
    p_model = np.array([0.55, 0.25, 0.20])
    prices = {"winamax_fr": np.array([2.0, 3.4, 4.0]), "unibet_fr": np.array([2.05, 3.3, 3.9])}
    cands = evaluate_match(match_id="m", league="F1", home="A", away="B", kickoff="2026-01-01T20:00", p_model=p_model,
                           prices=prices, policy=policy)
    assert len(cands) == 1
    c = cands[0]
    assert c.selection == "H" and c.bookmaker == "unibet_fr" and c.odds == 2.05
    assert abs(c.edge - (0.55 * 2.05 - 1)) < 1e-9
    assert 0 < c.stake <= 5.0
    assert c.stake % 0.5 == 0


def test_sharp_disagreement_filter():
    policy = StakingPolicy(require_sharp_agreement=True, sharp_tolerance=0.02)
    p_model = np.array([0.55, 0.25, 0.20])
    prices = {"book": np.array([2.0, 3.4, 4.0])}
    p_sharp = np.array([0.42, 0.30, 0.28])  # Pinnacle juge la cote 2.0 nettement trop basse (edge -16 %)
    assert evaluate_match(match_id="m", league="F1", home="A", away="B", kickoff="k", p_model=p_model, prices=prices,
                          policy=policy, p_sharp=p_sharp) == []
    policy.require_sharp_agreement = False
    assert len(evaluate_match(match_id="m", league="F1", home="A", away="B", kickoff="k", p_model=p_model, prices=prices,
                              policy=policy, p_sharp=p_sharp)) == 1


def test_select_daily_one_per_match_and_cap():
    policy = StakingPolicy(min_edge=0.0, max_bets_per_day=2, min_probability=0.0)
    cands = []
    for i, mid in enumerate(["m1", "m1", "m2", "m3"]):
        cands += evaluate_match(match_id=mid, league="F1", home="A", away="B", kickoff="k", p_model=np.array([0.5, 0.3, 0.2]),
                                prices={"b": np.array([2.3 + i * 0.1, 3.6, 5.5])}, policy=policy)
    chosen = select_daily(cands, policy)
    assert len(chosen) == 2
    assert len({c.match_id for c in chosen}) == 2
