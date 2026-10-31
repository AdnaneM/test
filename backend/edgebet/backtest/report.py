"""Rapport de backtest en Markdown (lisible dans GitHub, Telegram ou un éditeur)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from edgebet.backtest.engine import BacktestResult


def _fmt(v, pct: bool = False, digits: int = 3) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    if isinstance(v, int | float):
        return f"{v * 100:+.1f} %" if pct else f"{v:.{digits}f}"
    return str(v)


def md_table(rows: list[dict], columns: list[tuple[str, str]], pct_cols: set[str] | None = None) -> str:
    pct_cols = pct_cols or set()
    head = "| " + " | ".join(label for _, label in columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = []
    for r in rows:
        cells = []
        for key, _ in columns:
            v = r.get(key)
            if isinstance(v, int) and not isinstance(v, bool):
                cells.append(str(v))
            else:
                cells.append(_fmt(v, pct=key in pct_cols))
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *body])


def render_report(result: BacktestResult, title: str = "Backtest EdgeBet") -> str:
    m = result.metrics
    cfg = result.config
    lines = [f"# {title}", "", f"_Généré le {datetime.now():%d/%m/%Y %H:%M}_", ""]
    lines += [
        "## Protocole",
        "",
        f"- Saisons testées : {', '.join(sorted(result.weights))}",
        f"- Cotes jouées : `{cfg.odds_book}` · référence sharp : `{cfg.sharp_book}` · clôture : `{cfg.closing_book}`",
        f"- Politique : edge min {cfg.policy.min_edge:.0%}, Kelly ×{cfg.policy.kelly_fraction}, mise max {cfg.policy.max_stake_fraction:.0%} de la bankroll, cotes {cfg.policy.min_odds}–{cfg.policy.max_odds}, "
        f"max {cfg.policy.max_bets_per_day} paris/jour, filtre Pinnacle : {'oui' if cfg.policy.require_sharp_agreement else 'non'}",
        f"- Features marché dans le GBM : {'oui' if cfg.use_market_features else 'non'}",
        f"- Matchs évalués : {m['n_matches']} · paris simulés : {m['n_bets']}",
        "",
        "## Qualité des probabilités (toutes saisons testées)",
        "",
        "Plus la log-loss est basse, mieux c'est. `market_close` (Pinnacle clôture) est la référence quasi imbattable ; "
        "`market_open` est ce que l'on voit le matin ; `uniform` = 1/3 partout.",
        "",
    ]
    rows = [{"model": k, **v} for k, v in m["probability"]["all"].items()]
    lines.append(md_table(rows, [("model", "Modèle"), ("n", "n"), ("log_loss", "Log-loss"), ("brier", "Brier"), ("accuracy", "Précision")]))
    lines += ["", "## Par saison", ""]
    rows = []
    for key, vals in m["probability"].items():
        if key.startswith("season="):
            rows.append({"season": key.split("=", 1)[1], "final": vals["final"]["log_loss"], "gbm": vals["gbm"]["log_loss"],
                         "dc": vals["dixon_coles"]["log_loss"], "open": vals["market_open"]["log_loss"], "close": vals["market_close"]["log_loss"]})
    lines.append(md_table(rows, [("season", "Saison"), ("final", "Final"), ("gbm", "GBM"), ("dc", "Dixon-Coles"), ("open", "Marché ouv."), ("close", "Marché clôt.")]))
    lines += ["", "## Par ligue", ""]
    rows = []
    for key, vals in m["probability"].items():
        if key.startswith("league="):
            rows.append({"league": key.split("=", 1)[1], "n": vals["final"]["n"], "final": vals["final"]["log_loss"],
                         "open": vals["market_open"]["log_loss"], "close": vals["market_close"]["log_loss"]})
    lines.append(md_table(rows, [("league", "Ligue"), ("n", "n"), ("final", "Final"), ("open", "Marché ouv."), ("close", "Marché clôt.")]))
    lines += ["", "## Simulation de mise", "", "ROI = profit / total misé. CLV = écart moyen entre la cote prise et la cote juste de clôture "
              "(positif = on a battu la clôture, le meilleur indicateur d'une vraie edge).", ""]
    b = m["betting"]
    rows = [{"scope": "Kelly fractionné", **b["all"]}, {"scope": "Mise fixe", **b["all_flat"]}]
    for key in sorted(k for k in b if k.startswith("season=")):
        rows.append({"scope": key.replace("season=", "saison "), **b[key]})
    for key in sorted(k for k in b if k.startswith("league=")):
        rows.append({"scope": key.replace("league=", "ligue "), **b[key]})
    for key in sorted(k for k in b if k.startswith("risk=")):
        rows.append({"scope": key.replace("risk=", "risque "), **b[key]})
    lines.append(md_table(rows, [("scope", "Périmètre"), ("n_bets", "Paris"), ("staked", "Misé"), ("pnl", "P&L"), ("roi", "ROI"),
                                 ("hit_rate", "Réussite"), ("avg_odds", "Cote moy."), ("clv_mean", "CLV moy."), ("max_drawdown", "Drawdown max")],
                          pct_cols={"roi", "hit_rate", "clv_mean"}))
    lines += ["", "## Poids du mélange et température par saison", ""]
    rows = [{"season": s, **{k: round(v, 3) for k, v in w.items()}, "temperature": result.temperatures.get(s)} for s, w in result.weights.items()]
    cols = [("season", "Saison")] + [(c, c) for c in cfg.components] + [("temperature", "Température")]
    lines.append(md_table(rows, cols))
    lines += ["", "## Lecture honnête", "",
              "- Si la log-loss `final` n'est pas nettement sous `market_open`, le modèle n'apporte rien au-delà du marché.",
              "- Un ROI positif sur quelques centaines de paris n'est pas significatif ; regarder d'abord le CLV.",
              "- Les cotes `avg` sont réalistes pour un parieur français ; `max` surestime (toutes les cotes ne sont pas accessibles depuis la France).", ""]
    return "\n".join(lines)


def save_report(result: BacktestResult, out_dir: Path, stem: str = "backtest") -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md = out_dir / f"{stem}_{ts}.md"
    md.write_text(render_report(result), encoding="utf-8")
    js = out_dir / f"{stem}_{ts}.json"
    js.write_text(json.dumps({"metrics": result.metrics, "weights": result.weights, "temperatures": result.temperatures}, indent=2, default=str), encoding="utf-8")
    result.bets.to_csv(out_dir / f"{stem}_{ts}_bets.csv", index=False)
    return md, js
