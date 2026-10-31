# EdgeBet

Moteur personnel de recommandations de paris sportifs : il récupère chaque matin les cotes de Winamax,
Unibet et Betclic, les compare à un modèle de probabilités (Dixon-Coles + gradient boosting + marché
Pinnacle), détecte les *value bets*, calcule une mise de Kelly fractionnée et un score de risque, puis
envoie la grille sur Telegram avec des boutons « Joué / Passé » et l'affiche dans une PWA mobile.
Les paris se placent **à la main** (aucun bookmaker français n'autorise l'automatisation) ; EdgeBet
règle ensuite les paris avec les résultats et mesure le CLV face aux cotes de clôture.

> **Lecture honnête.** Les cotes de clôture des bookmakers intègrent presque toute l'information publique
> et les marges françaises tournent entre 6 et 8 %. L'espérance réaliste d'un modèle sur données publiques
> est proche de zéro. Le backtest est là pour le mesurer avant de miser ; le CLV est l'indicateur à suivre.

## Architecture

```
football-data.co.uk  ─┐                       ┌─> SQLite (recommandations, cotes, bankroll)
The Odds API (cotes) ─┼─> features causales ─> │
ClubElo / API-Football┘   Elo · forme · DC     ├─> API FastAPI  ──> PWA mobile (Grille · Historique · Stats)
                           GBM calibré         └─> Telegram (grille + boutons) <── n8n ou worker interne
```

* `backend/` : package Python `edgebet` (données, features, modèles, backtest, pipeline, API, Telegram, CLI).
* `frontend/` : PWA React/Vite (mode démo intégré).
* `deploy/` : Dockerfile backend, `docker-compose.yml` (api, worker, web), `.env.example`.
* `n8n/` : workflow d'orchestration optionnel (règlement + grille + alerte).
* `docs/` : [SPORTS.md](docs/SPORTS.md) (sports proposés), [MODEL.md](docs/MODEL.md) (méthode),
  [DEPLOY.md](docs/DEPLOY.md) (VPS, Telegram, clés API, n8n), [API.md](docs/API.md) (contrat HTTP).

## Démarrage local

```bash
make setup                 # venv Python (uv) + dépendances
make test                  # 20 tests : parsing, Elo, forme, Dixon-Coles, cotes, value, backtest, API, pipeline
cp deploy/.env.example backend/.env   # puis renseigner au moins EDGEBET_ODDS_API_KEY
cd backend && . .venv/bin/activate
edgebet download           # historique football-data.co.uk (12 saisons, 6 ligues)
edgebet backtest           # rapport Markdown dans backend/data/reports/
edgebet train              # modèle de production -> backend/data/models/bundle.joblib
edgebet run-daily          # grille du jour (ajouter --notify pour Telegram)
edgebet serve              # API sur http://localhost:8000/api/health
cd ../frontend && npm install && npm run dev   # PWA sur http://localhost:5173 (proxy /api -> :8000)
```

Toutes les commandes : `edgebet --help` (`info`, `download`, `backtest`, `train`, `run-daily`, `settle`,
`serve`, `worker`, `telegram-test`, `telegram-poll`, `init-db`).

## Configuration

Variables d'environnement préfixées `EDGEBET_` (voir `deploy/.env.example`) : ligues, bookmakers, clés
API, Telegram, bankroll et politique de mise, paramètres du modèle, heure d'envoi, base de données.

## État et prochaines étapes

| Étape | Contenu | État |
|-------|---------|------|
| 0 | Données, features, Dixon-Coles, GBM, mélange, backtest walk-forward, rapport | **Code prêt, testé sur données synthétiques ; backtest réel à lancer dès que le réseau/VPS est disponible** |
| 1 | Cotes live (The Odds API), grille quotidienne, SQLite, Telegram avec boutons, worker | Code prêt, à valider avec les clés |
| 2 | PWA (grille, historique, stats), API, Docker, n8n | Code prêt |
| 3 | Tennis (Elo par surface, données Sackmann), marchés plus/moins et BTTS | À faire |
| 4 | Basket (NBA, Euroligue), blessés et compositions dans le modèle | À faire |

## Cadre légal et bon sens

Paris sportifs réservés aux majeurs, auprès d'opérateurs agréés par l'ANJ. EdgeBet ne place aucun pari,
ne contourne aucune condition d'utilisation et ne garantit aucun gain. Jouer avec des sommes que l'on peut perdre.
