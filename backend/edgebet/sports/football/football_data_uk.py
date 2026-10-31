"""Chargement de l'historique football-data.co.uk.

Source gratuite et sans clé : résultats, statistiques de match et cotes
(ouverture et clôture) de plusieurs bookmakers, dont Pinnacle, depuis 1993.
URL : https://www.football-data.co.uk/mmz4281/<saison>/<division>.csv
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from edgebet.schema import LEAGUES, MATCH_BASE_COLUMNS, STAT_COLUMNS, make_match_id, result_from_goals

log = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/mmz4281/{code}/{div}.csv"

RENAME: dict[str, str] = {
    "Div": "div",
    "Date": "date_raw",
    "Time": "time_raw",
    "HomeTeam": "home",
    "AwayTeam": "away",
    "FTHG": "hg",
    "FTAG": "ag",
    "FTR": "result",
    "HTHG": "hthg",
    "HTAG": "htag",
    "HS": "shots_h",
    "AS": "shots_a",
    "HST": "sot_h",
    "AST": "sot_a",
    "HC": "corners_h",
    "AC": "corners_a",
    "HF": "fouls_h",
    "AF": "fouls_a",
    "HY": "yellow_h",
    "AY": "yellow_a",
    "HR": "red_h",
    "AR": "red_a",
    # 1X2 Pinnacle
    "PSH": "odds_ps_h",
    "PSD": "odds_ps_d",
    "PSA": "odds_ps_a",
    "PSCH": "odds_psc_h",
    "PSCD": "odds_psc_d",
    "PSCA": "odds_psc_a",
    # 1X2 Bet365
    "B365H": "odds_b365_h",
    "B365D": "odds_b365_d",
    "B365A": "odds_b365_a",
    "B365CH": "odds_b365c_h",
    "B365CD": "odds_b365c_d",
    "B365CA": "odds_b365c_a",
    # 1X2 moyenne / max du marché (nouveau et ancien format Betbrain)
    "AvgH": "odds_avg_h",
    "AvgD": "odds_avg_d",
    "AvgA": "odds_avg_a",
    "AvgCH": "odds_avgc_h",
    "AvgCD": "odds_avgc_d",
    "AvgCA": "odds_avgc_a",
    "MaxH": "odds_max_h",
    "MaxD": "odds_max_d",
    "MaxA": "odds_max_a",
    "MaxCH": "odds_maxc_h",
    "MaxCD": "odds_maxc_d",
    "MaxCA": "odds_maxc_a",
    "BbAvH": "odds_avg_h",
    "BbAvD": "odds_avg_d",
    "BbAvA": "odds_avg_a",
    "BbMxH": "odds_max_h",
    "BbMxD": "odds_max_d",
    "BbMxA": "odds_max_a",
    # Plus / moins 2.5 buts
    "P>2.5": "odds_ps_over25",
    "P<2.5": "odds_ps_under25",
    "PC>2.5": "odds_psc_over25",
    "PC<2.5": "odds_psc_under25",
    "B365>2.5": "odds_b365_over25",
    "B365<2.5": "odds_b365_under25",
    "Avg>2.5": "odds_avg_over25",
    "Avg<2.5": "odds_avg_under25",
    "AvgC>2.5": "odds_avgc_over25",
    "AvgC<2.5": "odds_avgc_under25",
    "Max>2.5": "odds_max_over25",
    "Max<2.5": "odds_max_under25",
    "BbAv>2.5": "odds_avg_over25",
    "BbAv<2.5": "odds_avg_under25",
    "BbMx>2.5": "odds_max_over25",
    "BbMx<2.5": "odds_max_under25",
}

NUMERIC_PREFIXES = ("odds_", "shots_", "sot_", "corners_", "fouls_", "yellow_", "red_")


def current_season_start(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def season_code(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_start_years(n_back: int, today: date | None = None) -> list[int]:
    cur = current_season_start(today)
    return list(range(cur - n_back + 1, cur + 1))


def csv_path(raw_dir: Path, start_year: int, div: str) -> Path:
    return Path(raw_dir) / "football-data" / f"{season_code(start_year)}_{div}.csv"


def download(
    start_year: int,
    div: str,
    raw_dir: Path,
    client: httpx.Client | None = None,
    force: bool = False,
    timeout: float = 30.0,
) -> Path | None:
    """Télécharge un CSV de saison (si absent ou ``force``). Retourne le chemin ou None en cas d'échec."""
    path = csv_path(raw_dir, start_year, div)
    if path.exists() and not force:
        return path
    url = BASE_URL.format(code=season_code(start_year), div=div)
    own_client = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(url)
        if resp.status_code != 200 or len(resp.content) < 200:
            log.warning("football-data: %s -> HTTP %s (%d octets)", url, resp.status_code, len(resp.content))
            return path if path.exists() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        log.info("football-data: %s téléchargé (%d octets)", path.name, len(resp.content))
        return path
    except httpx.HTTPError as exc:
        log.warning("football-data: échec %s : %s", url, exc)
        return path if path.exists() else None
    finally:
        if own_client:
            client.close()


def _read_csv(path: Path) -> pd.DataFrame:
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, on_bad_lines="skip", skip_blank_lines=True)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Impossible de lire {path}")


def parse(path: Path, div: str, start_year: int) -> pd.DataFrame:
    """Convertit un CSV football-data.co.uk vers le schéma canonique."""
    raw = _read_csv(path)
    raw = raw.loc[:, [c for c in raw.columns if not str(c).startswith("Unnamed")]]
    raw = raw.rename(columns=RENAME)
    raw = raw.loc[:, ~raw.columns.duplicated(keep="first")]

    if "home" not in raw.columns or "date_raw" not in raw.columns:
        log.warning("football-data: colonnes manquantes dans %s", path.name)
        return pd.DataFrame(columns=MATCH_BASE_COLUMNS)

    df = raw.dropna(subset=["home", "away", "date_raw"]).copy()
    df["date"] = pd.to_datetime(df["date_raw"].astype(str).str.strip(), dayfirst=True, format="mixed", errors="coerce")
    df = df.dropna(subset=["date"])
    if "time_raw" in df.columns:
        t = pd.to_datetime(df["time_raw"].astype(str).str.strip(), format="%H:%M", errors="coerce")
        has_t = t.notna()
        df.loc[has_t, "date"] = df.loc[has_t, "date"] + pd.to_timedelta(
            t[has_t].dt.hour * 60 + t[has_t].dt.minute, unit="m"
        )

    for col in ("hg", "ag"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan
    df = df.dropna(subset=["hg", "ag"])
    df["hg"] = df["hg"].astype(int)
    df["ag"] = df["ag"].astype(int)
    df["result"] = [result_from_goals(h, a) for h, a in zip(df["hg"], df["ag"], strict=True)]

    for col in df.columns:
        if str(col).startswith(NUMERIC_PREFIXES):
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if str(col).startswith("odds_"):
                df.loc[df[col] <= 1.0, col] = np.nan

    df["home"] = df["home"].astype(str).str.strip()
    df["away"] = df["away"].astype(str).str.strip()
    df["league"] = div
    df["sport"] = "football"
    df["season"] = season_label(start_year)
    df["match_id"] = [
        make_match_id(div, d, h, a) for d, h, a in zip(df["date"], df["home"], df["away"], strict=True)
    ]

    keep = [c for c in MATCH_BASE_COLUMNS if c in df.columns]
    keep += [c for c in STAT_COLUMNS if c in df.columns]
    keep += sorted(c for c in df.columns if str(c).startswith("odds_"))
    out = df[keep].sort_values("date").reset_index(drop=True)
    return out


def load_history(
    leagues: list[str],
    start_years: list[int],
    raw_dir: Path,
    download_missing: bool = True,
    refresh_current: bool = True,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Charge (et télécharge si besoin) l'historique de plusieurs ligues et saisons."""
    frames: list[pd.DataFrame] = []
    cur = current_season_start()
    own_client = client is None and download_missing
    client = client or (httpx.Client(timeout=30.0, follow_redirects=True) if download_missing else None)
    try:
        for div in leagues:
            if div not in LEAGUES:
                log.warning("Ligue inconnue ignorée : %s", div)
                continue
            for year in start_years:
                path = csv_path(raw_dir, year, div)
                if download_missing:
                    path = download(year, div, raw_dir, client=client, force=(refresh_current and year == cur)) or path
                if not path.exists():
                    log.warning("football-data: fichier absent %s", path.name)
                    continue
                try:
                    frames.append(parse(path, div, year))
                except Exception as exc:  # fichier corrompu : on continue
                    log.warning("football-data: parse impossible %s : %s", path.name, exc)
    finally:
        if own_client and client is not None:
            client.close()
    if not frames:
        return pd.DataFrame(columns=MATCH_BASE_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["match_id"]).sort_values(["date", "league"]).reset_index(drop=True)
    return df
