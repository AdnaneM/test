"""Forme récente des équipes : moyennes glissantes causales (shift(1) avant rolling)."""

from __future__ import annotations

import numpy as np
import pandas as pd

FORM_STATS = ["pts", "gf", "ga", "gd", "sf", "sa", "sotf", "sota"]


def team_match_long(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par équipe et par match (vue domicile + vue extérieur)."""

    def side(is_home: bool) -> pd.DataFrame:
        s = pd.DataFrame(
            {
                "match_id": df["match_id"].to_numpy(),
                "date": df["date"].to_numpy(),
                "league": df["league"].to_numpy(),
                "season": df["season"].to_numpy(),
                "team": (df["home"] if is_home else df["away"]).to_numpy(),
                "opp": (df["away"] if is_home else df["home"]).to_numpy(),
                "is_home": is_home,
                "gf": pd.to_numeric(df["hg" if is_home else "ag"], errors="coerce").to_numpy(dtype=float),
                "ga": pd.to_numeric(df["ag" if is_home else "hg"], errors="coerce").to_numpy(dtype=float),
            }
        )
        for src_h, src_a, name in (("shots_h", "shots_a", "s"), ("sot_h", "sot_a", "sot")):
            f = df[src_h if is_home else src_a] if src_h in df.columns and src_a in df.columns else np.nan
            a = df[src_a if is_home else src_h] if src_h in df.columns and src_a in df.columns else np.nan
            s[f"{name}f"] = pd.to_numeric(f, errors="coerce").to_numpy(dtype=float) if not np.isscalar(f) else np.nan
            s[f"{name}a"] = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float) if not np.isscalar(a) else np.nan
        return s

    long = pd.concat([side(True), side(False)], ignore_index=True)
    long["gd"] = long["gf"] - long["ga"]
    long["pts"] = np.select([long["gd"] > 0, long["gd"] == 0], [3.0, 1.0], default=0.0)
    long.loc[long["gf"].isna(), "pts"] = np.nan
    long = long.sort_values(["team", "date", "match_id"]).reset_index(drop=True)
    return long


def _rolling_prev(g: pd.core.groupby.SeriesGroupBy, window: int, min_periods: int) -> pd.Series:
    return g.transform(lambda s: s.shift(1).rolling(window, min_periods=min_periods).mean())


def add_form_features(df: pd.DataFrame, windows: tuple[int, ...] = (5, 10)) -> pd.DataFrame:
    """Ajoute, pour l'équipe à domicile (préfixe ``h_``) et à l'extérieur (``a_``) :

    ``<stat>_<w>`` moyennes glissantes avant match, ``rest`` jours de repos,
    ``season_matches`` matchs déjà joués dans la saison, ``home_pts_5`` / ``away_pts_5``
    forme spécifique au lieu.
    """
    long = team_match_long(df)
    g = long.groupby("team", sort=False)
    feats: dict[str, pd.Series] = {}
    for w in windows:
        mp = max(2, min(3, w))
        for stat in FORM_STATS:
            feats[f"{stat}_{w}"] = _rolling_prev(g[stat], w, mp)
    prev_date = g["date"].shift(1)
    feats["rest"] = (long["date"] - prev_date).dt.total_seconds() / 86400.0
    feats["season_matches"] = long.groupby(["team", "season"], sort=False).cumcount().astype(float)
    # forme spécifique au lieu (domicile pour l'équipe recevante, extérieur pour la visiteuse)
    venue = pd.Series(np.nan, index=long.index)
    for is_home in (True, False):
        mask = long["is_home"] == is_home
        sub = long.loc[mask]
        venue.loc[mask] = sub.groupby("team", sort=False)["pts"].transform(
            lambda s: s.shift(1).rolling(5, min_periods=2).mean()
        )
    feats["venue_pts_5"] = venue
    f = pd.DataFrame(feats, index=long.index)
    f["match_id"] = long["match_id"].to_numpy()
    f["is_home"] = long["is_home"].to_numpy()

    home_f = f[f["is_home"]].drop(columns="is_home").set_index("match_id").add_prefix("h_")
    away_f = f[~f["is_home"]].drop(columns="is_home").set_index("match_id").add_prefix("a_")
    out = df.merge(home_f, left_on="match_id", right_index=True, how="left")
    out = out.merge(away_f, left_on="match_id", right_index=True, how="left")
    out = out.rename(columns={"h_venue_pts_5": "h_home_pts_5", "a_venue_pts_5": "a_away_pts_5"})
    out["rest_diff"] = out["h_rest"].clip(upper=30) - out["a_rest"].clip(upper=30)
    for w in windows:
        out[f"pts_diff_{w}"] = out[f"h_pts_{w}"] - out[f"a_pts_{w}"]
        out[f"gd_diff_{w}"] = out[f"h_gd_{w}"] - out[f"a_gd_{w}"]
    return out
