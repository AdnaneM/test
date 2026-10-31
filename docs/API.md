# API HTTP

Base : `http://<hôte>:8000/api` (ou `/api` derrière le reverse proxy de la PWA). JSON partout. Les
endpoints d'écriture exigent l'en-tête `X-API-Key: <EDGEBET_API_KEY>`.

| Méthode | Chemin | Rôle |
|---------|--------|------|
| GET | `/api/health` | état, version, heure |
| GET | `/api/grid?date=YYYY-MM-DD` | grille du jour (défaut : aujourd'hui) : `summary` + `items` |
| GET | `/api/recommendations?from&to&decision&outcome&limit` | historique filtrable (`decision` : pending/played/skipped ; `outcome` : open/won/lost/void) |
| POST | `/api/recommendations/{id}/mark` 🔑 | corps `{"decision":"played"|"skipped"|"pending","stake":2.0,"odds":2.1}` |
| GET | `/api/stats` | bankroll, P&L, ROI, réussite, CLV, par ligue, par risque, courbe de bankroll, calibration |
| GET | `/api/runs?limit=20` | exécutions du pipeline, crédits The Odds API restants |
| POST | `/api/pipeline/run?notify=true` 🔑 | lance la grille du jour (et Telegram si `notify`) |
| POST | `/api/pipeline/settle` 🔑 | règle les paris passés |

## Objet `Recommendation`

```json
{
  "id": 12, "created_at": "2026-10-31T09:00:12",
  "match_id": "F1:2026-11-01:paris-sg:marseille", "league": "F1", "league_name": "Ligue 1",
  "home": "Paris SG", "away": "Marseille", "kickoff": "2026-11-01T20:45",
  "market": "1X2", "selection": "H", "selection_label": "Victoire domicile", "pick_label": "Paris SG",
  "p_model": 0.512, "p_sharp": 0.49, "odds": 2.10, "bookmaker": "winamax_fr", "bookmaker_label": "Winamax",
  "bookmaker_url": "https://www.winamax.fr/paris-sportifs/sports/1",
  "fair_odds_sharp": 2.04, "edge": 0.075, "edge_vs_sharp": 0.03, "kelly": 0.068, "stake": 2.0, "risk": 2,
  "components": {"gbm": 0.50, "dc": 0.53, "market": 0.49},
  "decision": "pending", "outcome": "open",
  "odds_taken": null, "stake_taken": null, "result": null, "score": null, "pnl": null, "closing_odds": null, "clv": null
}
```

* `selection` : `H` domicile, `D` nul, `A` extérieur. `kickoff` : heure locale Europe/Paris.
* `edge` = p_modèle × cote − 1 ; `edge_vs_sharp` = même calcul avec la probabilité Pinnacle sans marge.
* `risk` : 1 (sûr) à 5 (spéculatif).
* Après règlement : `outcome`, `result`, `score`, `pnl` (réel si joué, théorique sinon), `closing_odds`
  et `clv` (cote prise × probabilité juste de clôture − 1).

## Exemple n8n / curl

```bash
curl -s -X POST "http://localhost:8000/api/pipeline/run?notify=true" -H "X-API-Key: $EDGEBET_API_KEY"
curl -s "http://localhost:8000/api/grid" | jq '.summary'
curl -s -X POST "http://localhost:8000/api/recommendations/12/mark" -H "X-API-Key: $EDGEBET_API_KEY" \
     -H "Content-Type: application/json" -d '{"decision":"played","stake":2}'
```
