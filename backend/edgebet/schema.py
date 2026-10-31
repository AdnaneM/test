"""Schéma canonique des matchs et registre des compétitions.

Un match est une ligne d'un DataFrame pandas avec au minimum les colonnes
``match_id, sport, league, season, date, home, away, hg, ag, result``.
Les cotes suivent la convention ``odds_<book>_<h|d|a>`` et
``odds_<book>_<over25|under25>``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class League:
    code: str  # code football-data.co.uk
    name: str
    country: str
    odds_api_key: str  # clé "sport" chez The Odds API
    api_football_id: int
    tier: int


LEAGUES: dict[str, League] = {
    "F1": League("F1", "Ligue 1", "FR", "soccer_france_ligue_one", 61, 1),
    "F2": League("F2", "Ligue 2", "FR", "soccer_france_ligue_two", 62, 2),
    "E0": League("E0", "Premier League", "EN", "soccer_epl", 39, 1),
    "E1": League("E1", "Championship", "EN", "soccer_efl_champ", 40, 2),
    "SP1": League("SP1", "La Liga", "ES", "soccer_spain_la_liga", 140, 1),
    "SP2": League("SP2", "La Liga 2", "ES", "soccer_spain_segunda_division", 141, 2),
    "D1": League("D1", "Bundesliga", "DE", "soccer_germany_bundesliga", 78, 1),
    "D2": League("D2", "2. Bundesliga", "DE", "soccer_germany_bundesliga2", 79, 2),
    "I1": League("I1", "Serie A", "IT", "soccer_italy_serie_a", 135, 1),
    "I2": League("I2", "Serie B", "IT", "soccer_italy_serie_b", 136, 2),
    "N1": League("N1", "Eredivisie", "NL", "soccer_netherlands_eredivisie", 88, 1),
    "P1": League("P1", "Primeira Liga", "PT", "soccer_portugal_primeira_liga", 94, 1),
    "B1": League("B1", "Jupiler Pro League", "BE", "soccer_belgium_first_div", 144, 1),
    "T1": League("T1", "Süper Lig", "TR", "soccer_turkey_super_league", 203, 1),
    "SC0": League("SC0", "Scottish Premiership", "SC", "soccer_spl", 179, 1),
}

LEAGUE_CODE_INDEX: dict[str, int] = {code: i for i, code in enumerate(LEAGUES)}
ODDS_API_KEY_TO_LEAGUE: dict[str, str] = {lg.odds_api_key: code for code, lg in LEAGUES.items()}

OUTCOMES: list[str] = ["H", "D", "A"]
RESULT_CODES: dict[str, int] = {"H": 0, "D": 1, "A": 2}
OUTCOME_LABELS_FR: dict[str, str] = {"H": "Victoire domicile", "D": "Match nul", "A": "Victoire extérieur"}

ODDS_BOOKS: dict[str, str] = {
    "ps": "Pinnacle (ouverture)",
    "psc": "Pinnacle (clôture)",
    "b365": "Bet365 (ouverture)",
    "b365c": "Bet365 (clôture)",
    "avg": "Moyenne du marché (ouverture)",
    "avgc": "Moyenne du marché (clôture)",
    "max": "Meilleure cote du marché (ouverture)",
    "maxc": "Meilleure cote du marché (clôture)",
}

MATCH_BASE_COLUMNS: list[str] = [
    "match_id",
    "sport",
    "league",
    "season",
    "date",
    "home",
    "away",
    "hg",
    "ag",
    "result",
]

STAT_COLUMNS: list[str] = [
    "shots_h",
    "shots_a",
    "sot_h",
    "sot_a",
    "corners_h",
    "corners_a",
    "fouls_h",
    "fouls_a",
    "yellow_h",
    "yellow_a",
    "red_h",
    "red_a",
]


def odds_cols(book: str) -> list[str]:
    return [f"odds_{book}_h", f"odds_{book}_d", f"odds_{book}_a"]


def result_from_goals(hg: float | int | None, ag: float | int | None) -> str | None:
    if hg is None or ag is None or pd.isna(hg) or pd.isna(ag):
        return None
    if hg > ag:
        return "H"
    if hg < ag:
        return "A"
    return "D"


def slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value)).strip("-")


def make_match_id(league: str, date: pd.Timestamp, home: str, away: str) -> str:
    d = pd.Timestamp(date).strftime("%Y-%m-%d")
    return f"{league}:{d}:{slug(home)}:{slug(away)}"


def ensure_match_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Garantit la présence des colonnes de base (ajoutées vides si absentes)."""
    out = df.copy()
    for col in MATCH_BASE_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    if "sport" in out.columns:
        out["sport"] = out["sport"].fillna("football")
    out["date"] = pd.to_datetime(out["date"])
    return out
