import numpy as np

from edgebet.models.dixon_coles import fit_dixon_coles, outcome_probs, predict_match, score_matrix


def test_recovers_parameters(league_df):
    df, truth = league_df
    last_year = max(truth["attack"])
    sub = df[df["season"].str.startswith(str(last_year))]
    params = fit_dixon_coles(sub, xi=0.0)
    true_att = np.array([truth["attack"][last_year][t] for t in params.teams])
    true_def = np.array([truth["defense"][last_year][t] for t in params.teams])
    # une seule saison (34 matchs par équipe) : l'erreur-type d'une force d'attaque est ~0,15 pour un écart-type vrai de 0,30
    assert np.corrcoef(params.attack, true_att)[0, 1] > 0.75
    assert np.corrcoef(params.defense, true_def)[0, 1] > 0.6
    assert abs(params.home_adv - truth["home_adv"]) < 0.15
    assert -0.3 < params.rho < 0.1


def test_score_matrix_is_distribution():
    m = score_matrix(1.6, 1.1, -0.08)
    assert abs(m.sum() - 1.0) < 1e-9
    p = outcome_probs(m)
    assert abs(p["p_h"] + p["p_d"] + p["p_a"] - 1.0) < 1e-9
    assert p["p_h"] > p["p_a"]
    assert 0 < p["p_over25"] < 1 and 0 < p["p_btts"] < 1


def test_unknown_team_falls_back_to_average(league_df):
    df, _ = league_df
    params = fit_dixon_coles(df[df["season"] == df["season"].max()], xi=0.001)
    pr = predict_match(params, "Inconnu FC", params.teams[0])
    assert 0 < pr["p_h"] < 1 and abs(pr["p_h"] + pr["p_d"] + pr["p_a"] - 1) < 1e-9


def test_warm_start_matches_cold_start(league_df):
    df, _ = league_df
    sub = df[df["season"] == df["season"].max()]
    cold = fit_dixon_coles(sub, xi=0.0)
    warm = fit_dixon_coles(sub, xi=0.0, init=cold)
    assert np.allclose(cold.attack, warm.attack, atol=0.02)
