import numpy as np

from edgebet.backtest.engine import BacktestConfig, run_backtest
from edgebet.backtest.report import render_report
from edgebet.betting.value import StakingPolicy
from edgebet.features.build import FEATURES, FeatureConfig, build_feature_frame
from edgebet.pipeline.train import train_bundle

CFG = FeatureConfig(dc_xi=0.002, dc_refit_days=7, dc_window_days=800, dc_min_matches=120)


def test_features_are_causal(league_df):
    df, _ = league_df
    feats, _ = build_feature_frame(df, CFG)
    cutoff = feats["date"].quantile(0.6)
    # on falsifie tous les résultats après la coupure : rien ne doit changer avant
    tampered = df.copy()
    late = tampered["date"] > cutoff
    tampered.loc[late, ["hg", "ag"]] = tampered.loc[late, ["ag", "hg"]].to_numpy()
    tampered.loc[late, "result"] = tampered.loc[late].apply(lambda r: "H" if r.hg > r.ag else "A" if r.hg < r.ag else "D", axis=1)
    feats2, _ = build_feature_frame(tampered, CFG)
    cols = [c for c in FEATURES if c in feats.columns]
    before = feats[feats["date"] <= cutoff][cols].to_numpy(dtype=float)
    before2 = feats2[feats2["date"] <= cutoff][cols].to_numpy(dtype=float)
    assert np.allclose(np.nan_to_num(before, nan=-999), np.nan_to_num(before2, nan=-999))


def test_backtest_beats_uniform_and_reports(league_df):
    df, _ = league_df
    feats, _ = build_feature_frame(df, CFG)
    assert feats["dc_p_h"].notna().mean() > 0.85
    policy = StakingPolicy(min_edge=0.02, max_bets_per_day=4, require_sharp_agreement=False)
    cfg = BacktestConfig(n_test_seasons=1, min_train_seasons=3, odds_book="avg", policy=policy)
    res = run_backtest(feats, cfg)
    m = res.metrics["probability"]["all"]
    assert m["final"]["log_loss"] < np.log(3) - 0.02
    assert m["final"]["log_loss"] < m["market_open"]["log_loss"] + 0.01  # cotes bruitées : le modèle fait au moins aussi bien
    assert m["market_close"]["log_loss"] < np.log(3)
    assert res.bets.shape[0] > 0
    assert set(["date", "selection", "odds", "stake", "pnl", "clv", "won"]) <= set(res.bets.columns)
    report = render_report(res)
    assert "Log-loss" in report and "CLV" in report


def test_train_bundle_roundtrip(league_df, tmp_path):
    df, _ = league_df
    feats, _ = build_feature_frame(df, CFG)
    bundle = train_bundle(feats, CFG, min_matches_in_season=100)
    assert abs(sum(bundle.weights.values()) - 1) < 1e-6
    path = bundle.save(tmp_path / "bundle.joblib")
    from edgebet.models.bundle import ModelBundle

    loaded = ModelBundle.load(path)
    sample = feats[feats["dc_p_h"].notna()].tail(20)
    p = loaded.gbm.predict_proba(sample)
    assert p.shape == (20, 3) and np.allclose(p.sum(axis=1), 1.0)
