"""Configuration centrale.

Toutes les options se règlent par variables d'environnement préfixées ``EDGEBET_``
(ou dans un fichier ``.env``). Les listes sont des chaînes séparées par des virgules.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def split_csv(value: str) -> list[str]:
    return [v.strip() for v in str(value).split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EDGEBET_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Stockage -------------------------------------------------------
    data_dir: Path = Path("data")
    database_url: str = ""  # vide => SQLite dans data_dir

    # --- Périmètre sportif ---------------------------------------------
    sport: str = "football"
    leagues: str = "F1,F2,E0,SP1,D1,I1"
    seasons_back: int = 12

    # --- Bookmakers (clés The Odds API) --------------------------------
    bookmakers: str = "winamax_fr,unibet_fr,betclic"
    sharp_bookmaker: str = "pinnacle"
    odds_regions: str = "eu,fr"
    odds_markets: str = "h2h"

    # --- Clés et secrets -----------------------------------------------
    odds_api_key: str = ""
    api_football_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    api_key: str = ""  # protège les endpoints d'écriture de l'API

    # --- Bankroll et mise ----------------------------------------------
    bankroll: float = 100.0
    kelly_fraction: float = 0.25
    max_stake_fraction: float = 0.05
    min_edge: float = 0.03
    min_odds: float = 1.30
    max_odds: float = 6.0
    min_probability: float = 0.12
    max_bets_per_day: int = 6
    require_sharp_agreement: bool = True
    sharp_tolerance: float = 0.02

    # --- Modèle ----------------------------------------------------------
    dc_xi: float = 0.002  # décroissance temporelle Dixon-Coles (par jour)
    dc_refit_days: int = 7
    dc_window_days: int = 1100
    dc_min_matches: int = 120
    devig_method: Literal["multiplicative", "power", "shin"] = "power"
    gbm_min_train_seasons: int = 3

    # --- Planification -----------------------------------------------------
    timezone: str = "Europe/Paris"
    notify_hour: int = 9
    notify_minute: int = 0
    horizon_hours: int = 36
    settle_weekday: int = 1  # 0 = lundi ; football-data.co.uk se met à jour en début de semaine

    # --- Liens profonds vers les applis bookmakers -----------------------
    bookmaker_links: str = (
        "winamax_fr=https://www.winamax.fr/paris-sportifs/sports/1,"
        "unibet_fr=https://www.unibet.fr/sport/football,"
        "betclic=https://www.betclic.fr/football-s1"
    )

    @property
    def league_list(self) -> list[str]:
        return split_csv(self.leagues)

    @property
    def bookmaker_list(self) -> list[str]:
        return split_csv(self.bookmakers)

    @property
    def market_list(self) -> list[str]:
        return split_csv(self.odds_markets)

    @property
    def bookmaker_link_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in split_csv(self.bookmaker_links):
            if "=" in item:
                k, v = item.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'edgebet.db').resolve()}"

    @property
    def raw_dir(self) -> Path:
        p = self.data_dir / "raw"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def models_dir(self) -> Path:
        p = self.data_dir / "models"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_dir(self) -> Path:
        p = self.data_dir / "reports"
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
