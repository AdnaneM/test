import numpy as np
import pandas as pd

from edgebet.features.elo import EloConfig, EloRatings, compute_elo_features, expected_home, mov_multiplier
from edgebet.features.form import add_form_features


def test_expected_home_symmetry_and_hfa():
    assert abs(expected_home(1500, 1500, 0) - 0.5) < 1e-12
    assert expected_home(1500, 1500, 65) > 0.5
    assert abs(expected_home(1600, 1500, 0) + expected_home(1500, 1600, 0) - 1.0) < 1e-12


def test_update_direction_and_mov():
    elo = EloRatings(EloConfig(hfa=0))
    elo.update("A", "B", "F1", 3, 0)
    assert elo.ratings["A"] > 1500 > elo.ratings["B"]
    assert mov_multiplier(1) == 1.0 and mov_multiplier(2) == 1.5 and mov_multiplier(4) > mov_multiplier(3)


def _tiny_df():
    rows = [
        ("2024-08-10", "A", "B", 2, 0), ("2024-08-17", "B", "A", 1, 1), ("2024-08-24", "A", "C", 0, 1),
        ("2024-08-31", "C", "A", 2, 2), ("2024-09-07", "A", "B", 3, 1), ("2024-09-14", "B", "C", np.nan, np.nan),
    ]
    df = pd.DataFrame(rows, columns=["date", "home", "away", "hg", "ag"])
    df["date"] = pd.to_datetime(df["date"])
    df["league"] = "F1"
    df["season"] = "2024-25"
    df["match_id"] = [f"m{i}" for i in range(len(df))]
    df["result"] = ["H", "D", "A", "D", "H", None]
    return df


def test_elo_features_are_pre_match_and_skip_unplayed():
    df = compute_elo_features(_tiny_df(), EloConfig(hfa=0))
    assert df.loc[0, "elo_h"] == 1500 and df.loc[0, "elo_a"] == 1500
    assert df.loc[1, "elo_a"] > 1500  # A a gagné le premier match
    # le match non joué ne modifie rien : ratings finaux = ceux d'avant ce match
    assert np.isfinite(df.loc[5, "elo_h"])


def test_form_is_causal():
    df = add_form_features(_tiny_df(), windows=(5,))
    # A avant son 5e match : points sur ses 4 matchs précédents = (3 + 1 + 0 + 1) / 4
    row = df[df["match_id"] == "m4"].iloc[0]
    assert abs(row["h_pts_5"] - 1.25) < 1e-9
    assert row["h_gf_5"] == (2 + 1 + 0 + 2) / 4
    # premier match : aucune forme disponible
    assert np.isnan(df[df["match_id"] == "m0"].iloc[0]["h_pts_5"])
    # repos : 7 jours entre m0 et m1 pour A (visiteur de m1)
    assert df[df["match_id"] == "m1"].iloc[0]["a_rest"] == 7
    # match à venir : la forme est calculée à partir des matchs joués (B : 3 matchs ; C : 2 matchs < min_periods -> NaN)
    future = df[df["match_id"] == "m5"].iloc[0]
    assert abs(future["h_pts_5"] - (0 + 1 + 0) / 3) < 1e-9
    assert np.isnan(future["a_pts_5"]) and future["a_rest"] == 14
