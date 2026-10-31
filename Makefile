# Raccourcis de développement et d'exploitation EdgeBet
PY := backend/.venv/bin/python
EDGEBET := backend/.venv/bin/edgebet

.PHONY: setup test lint download backtest train daily settle serve worker web-build up down logs

setup:            ## Environnement Python local (uv) + dépendances
	cd backend && uv venv .venv -q && uv pip install -q -e ".[dev]"

test:             ## Tests backend
	cd backend && .venv/bin/python -m pytest -q

lint:             ## Lint backend
	cd backend && .venv/bin/ruff check edgebet tests

download:         ## Historique football-data.co.uk
	cd backend && .venv/bin/edgebet download

backtest:         ## Backtest walk-forward (3 dernières saisons, cotes moyennes du marché)
	cd backend && .venv/bin/edgebet backtest --seasons 3 --book avg

train:            ## Entraîne le modèle de production
	cd backend && .venv/bin/edgebet train

daily:            ## Grille du jour (sans Telegram)
	cd backend && .venv/bin/edgebet run-daily

settle:           ## Règlement des paris passés
	cd backend && .venv/bin/edgebet settle

serve:            ## API locale sur :8000
	cd backend && .venv/bin/edgebet serve --reload

worker:           ## Planificateur + écoute Telegram
	cd backend && .venv/bin/edgebet worker

web-build:        ## Build de la PWA
	cd frontend && npm install && npm run build

up:               ## Déploiement Docker (VPS)
	cd deploy && docker compose --env-file .env up -d --build

down:
	cd deploy && docker compose down

logs:
	cd deploy && docker compose logs -f --tail=200
