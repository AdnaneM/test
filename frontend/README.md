# EdgeBet – frontend

PWA mobile-first (Vite + React 18 + TypeScript, CSS pur, graphiques SVG maison) pour consulter la
grille de paris du jour, l'historique et les statistiques du moteur EdgeBet.

## Développement

```bash
npm install
npm run dev          # http://localhost:5173, /api proxifié vers http://localhost:8000
```

Le backend FastAPI doit tourner sur le port 8000 (`/api/health`, `/api/grid`, `/api/recommendations`,
`/api/stats`, `/api/runs`).

## Build

```bash
npm run build        # tsc -b (zéro erreur TypeScript) puis vite build -> dist/
npm run preview      # sert dist/ en local
```

### Docker

```bash
docker build -t edgebet-frontend .
```

Image multi-étapes (node:22-alpine → nginx:1.27-alpine). nginx sert la SPA (repli sur `index.html`)
et proxifie `/api/` vers `http://api:8000/api/` (service `api` du docker-compose).

## Mode démo

Dans les réglages (icône ⚙️), activez **Mode démo** : l'application fonctionne sans backend avec un
jeu de données fictif mais réaliste (Ligue 1, Premier League, La Liga… ; Winamax, Unibet, Betclic).
Les actions « Joué / Passé / Annuler » sont conservées en mémoire le temps de la session.
En cas d'erreur de connexion, le bandeau d'erreur propose aussi d'activer ce mode.

## Réglages

| Réglage | Rôle |
| --- | --- |
| URL de l'API | Base de l'API (`""` = même origine, via le proxy nginx/Vite). |
| Clé API | Envoyée dans l'en-tête `X-API-Key` sur les écritures (`POST /api/recommendations/{id}/mark`). |
| Mode démo | Bascule sur les données fictives intégrées. |
| Tester la connexion | Appelle `GET /api/health` et affiche la version du backend. |

Les réglages sont persistés dans `localStorage` (clé `edgebet.settings.v1`).

## PWA

`public/manifest.webmanifest` (icônes SVG dans `public/icons/`) et `public/sw.js` : coquille applicative
en cache, navigations et `/api` en *network-first* avec repli hors ligne. Le service worker n'est
enregistré qu'en production (`import.meta.env.PROD`).
