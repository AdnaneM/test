"""Interface en ligne de commande : `edgebet --help`."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from edgebet import __version__
from edgebet.config import get_settings
from edgebet.schema import LEAGUES

app = typer.Typer(help="EdgeBet : moteur de recommandations de paris sportifs.", no_args_is_help=True)
console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Logs détaillés")) -> None:
    _setup_logging(verbose)


@app.command()
def info() -> None:
    """Affiche la configuration effective (sans les secrets)."""
    s = get_settings()
    t = Table(title=f"EdgeBet {__version__}")
    t.add_column("Paramètre")
    t.add_column("Valeur")
    for k, v in s.model_dump().items():
        if any(x in k for x in ("key", "token")):
            v = "défini" if v else "ABSENT"
        t.add_row(k, str(v))
    t.add_row("db_url", s.db_url)
    console.print(t)
    t2 = Table(title="Ligues configurées")
    t2.add_column("Code")
    t2.add_column("Nom")
    t2.add_column("Clé The Odds API")
    for code in s.league_list:
        lg = LEAGUES.get(code)
        t2.add_row(code, lg.name if lg else "?", lg.odds_api_key if lg else "?")
    console.print(t2)


@app.command()
def download(force: bool = typer.Option(False, help="Retélécharger même si présent")) -> None:
    """Télécharge l'historique football-data.co.uk pour les ligues et saisons configurées."""
    from edgebet.sports.football.football_data_uk import load_history, season_start_years

    s = get_settings()
    years = season_start_years(s.seasons_back)
    df = load_history(s.league_list, years, s.raw_dir, download_missing=True, refresh_current=True)
    if force:
        for p in (s.raw_dir / "football-data").glob("*.csv"):
            p.unlink()
        df = load_history(s.league_list, years, s.raw_dir, download_missing=True, refresh_current=True)
    console.print(f"[green]{len(df)} matchs[/green] sur {df['season'].nunique() if not df.empty else 0} saisons, {df['league'].nunique() if not df.empty else 0} ligues")
    if not df.empty:
        t = Table(title="Couverture")
        t.add_column("Ligue")
        t.add_column("Matchs")
        t.add_column("Première saison")
        t.add_column("Dernière date")
        t.add_column("Cotes Pinnacle clôture")
        for lg, sub in df.groupby("league"):
            psc = f"{sub['odds_psc_h'].notna().mean():.0%}" if "odds_psc_h" in sub else "0 %"
            t.add_row(str(lg), str(len(sub)), str(sub["season"].min()), str(sub["date"].max().date()), psc)
        console.print(t)


def _load_features(s, refresh: bool = False):
    from edgebet.features.build import build_feature_frame
    from edgebet.pipeline.daily import feature_config_from_settings
    from edgebet.sports.football.football_data_uk import load_history, season_start_years

    history = load_history(s.league_list, season_start_years(s.seasons_back), s.raw_dir, download_missing=refresh, refresh_current=refresh)
    if history.empty:
        raise typer.BadParameter("Historique vide : lancer d'abord `edgebet download`")
    console.print(f"Historique : {len(history)} matchs. Calcul des features (Elo, forme, Dixon-Coles)…")
    features, _ = build_feature_frame(history, feature_config_from_settings(s))
    return features


@app.command()
def backtest(
    seasons: int = typer.Option(3, help="Nombre de saisons de test (les plus récentes)"),
    book: str = typer.Option("avg", help="Cotes jouées : avg | max | b365 | ps"),
    no_market: bool = typer.Option(False, help="Ne pas donner les cotes Pinnacle au GBM"),
    min_edge: float = typer.Option(None, help="Edge minimum (défaut : config)"),
    out: Path = typer.Option(None, help="Dossier de sortie du rapport"),
) -> None:
    """Backtest walk-forward sur l'historique local et rapport Markdown."""
    from edgebet.backtest.engine import BacktestConfig, run_backtest
    from edgebet.backtest.report import render_report, save_report
    from edgebet.pipeline.daily import policy_from_settings

    s = get_settings()
    features = _load_features(s)
    policy = policy_from_settings(s)
    if min_edge is not None:
        policy.min_edge = min_edge
    cfg = BacktestConfig(n_test_seasons=seasons, odds_book=book, use_market_features=not no_market, policy=policy, devig_method=s.devig_method)
    result = run_backtest(features, cfg)
    md, js = save_report(result, out or s.reports_dir)
    console.print(render_report(result))
    console.print(f"\nRapport : [bold]{md}[/bold]\nMétriques : {js}")


@app.command()
def train(no_market: bool = typer.Option(False, help="Ne pas donner les cotes Pinnacle au GBM")) -> None:
    """Entraîne le modèle de production et l'enregistre dans data/models/bundle.joblib."""
    from edgebet.pipeline.daily import bundle_path, feature_config_from_settings
    from edgebet.pipeline.train import train_bundle

    s = get_settings()
    features = _load_features(s)
    bundle = train_bundle(features, feature_config_from_settings(s), use_market_features=not no_market)
    path = bundle.save(bundle_path(s))
    console.print(f"[green]Modèle enregistré[/green] : {path}")
    console.print(json.dumps(bundle.metrics, indent=2, default=str))
    console.print(f"Poids du mélange : {bundle.weights} · température : {bundle.temperature:.2f}")


@app.command("run-daily")
def run_daily_cmd(
    notify: bool = typer.Option(False, help="Envoyer la grille sur Telegram"),
    dry_run: bool = typer.Option(False, help="Ne rien écrire en base"),
) -> None:
    """Récupère les cotes du jour, prédit, détecte les value bets et enregistre la grille."""
    from edgebet.pipeline.daily import run_daily

    s = get_settings()
    res = run_daily(s, notify=notify and not dry_run, persist=not dry_run)
    console.print(f"[bold]{res.message}[/bold] · événements : {res.n_events} · crédits restants : {res.credits_remaining}")
    for w in res.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")
    if res.recommendations:
        t = Table(title="Grille")
        for col in ("Match", "Coup d'envoi", "Pari", "Cote", "Book", "Edge", "Mise", "Risque"):
            t.add_column(col)
        for r in res.recommendations:
            pick = r.get("pick_label") or r.get("selection_label")
            t.add_row(f"{r['home']} – {r['away']}", str(r.get("kickoff", ""))[:16], str(pick), f"{r['odds']:.2f}",
                      str(r.get("bookmaker_label") or r["bookmaker"]), f"{r['edge']:+.1%}", f"{r['stake']:.2f} €", "★" * int(r["risk"]))
        console.print(t)


@app.command()
def settle() -> None:
    """Règle les paris passés avec les résultats et cotes de clôture de football-data.co.uk."""
    from edgebet.pipeline.settle import run_settle

    res = run_settle(get_settings())
    console.print(res["message"])


@app.command("init-db")
def init_db_cmd() -> None:
    """Crée les tables de la base."""
    from edgebet.db.session import init_db

    s = get_settings()
    init_db(s.db_url)
    console.print(f"Base prête : {s.db_url}")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
    """Lance l'API HTTP."""
    import uvicorn

    uvicorn.run("edgebet.api.main:app", host=host, port=port, reload=reload)


@app.command()
def worker() -> None:
    """Planificateur : règlement + grille quotidienne à l'heure configurée, écoute Telegram."""
    from edgebet.worker import main_loop

    main_loop(get_settings())


@app.command("telegram-test")
def telegram_test() -> None:
    """Envoie un message de test sur Telegram."""
    from edgebet.notify.telegram import send_text

    send_text(get_settings(), f"✅ EdgeBet connecté ({datetime.now():%d/%m/%Y %H:%M})")
    console.print("Message envoyé")


@app.command("telegram-poll")
def telegram_poll() -> None:
    """Écoute les boutons Joué / Passé (long polling, sans webhook)."""
    from edgebet.notify.telegram import poll_forever

    poll_forever(get_settings())


if __name__ == "__main__":
    app()
