# Déploiement sur le VPS Hostinger

## 1. Prérequis

* Docker et le plugin `docker compose` (déjà présents si n8n a été installé via le template Hostinger).
* Un sous-domaine pour la PWA (par ex. `edgebet.mondomaine.fr`) : l'installation d'une PWA sur
  téléphone exige HTTPS.
* Les comptes et clés ci-dessous.

## 2. Clés et comptes à créer

| Service | Pour quoi | Comment | Coût |
|---------|-----------|---------|------|
| **The Odds API** | cotes Winamax, Unibet, Betclic, Pinnacle | https://the-odds-api.com → compte → clé | gratuit jusqu'à ~500 crédits/mois ; 6 ligues × 2 régions × 1 marché = 12 crédits par run, soit ~360/mois |
| **Telegram** | grille + boutons | parler à `@BotFather` → `/newbot` → jeton ; envoyer un message au bot puis ouvrir `https://api.telegram.org/bot<JETON>/getUpdates` et lire `chat.id` | gratuit |
| API-Football (optionnel) | blessés, compositions, calendrier | https://dashboard.api-football.com | gratuit, 100 requêtes/jour |
| football-data.co.uk, ClubElo | historique, Elo | aucune clé | gratuit |

## 3. Installation

```bash
git clone https://github.com/AdnaneM/test.git edgebet && cd edgebet
cp deploy/.env.example deploy/.env
nano deploy/.env            # clés, Telegram, bankroll, EDGEBET_API_KEY (mot de passe de l'API)
cd deploy
docker compose --env-file .env up -d --build
docker compose exec api edgebet info
```

Première initialisation (une fois, quelques minutes) :

```bash
docker compose exec api edgebet download        # 12 saisons × 6 ligues depuis football-data.co.uk
docker compose exec api edgebet backtest        # rapport dans le volume : data/reports/*.md
docker compose exec api edgebet train           # modèle de production
docker compose exec api edgebet telegram-test   # message de test sur le téléphone
docker compose exec api edgebet run-daily --dry-run   # grille sans écriture en base
```

Le service `worker` lance ensuite chaque jour, à `EDGEBET_NOTIFY_HOUR:EDGEBET_NOTIFY_MINUTE`
(Europe/Paris) : règlement des paris passés, puis grille du jour et envoi Telegram. Il écoute aussi les
boutons « Joué / Passé » (long polling, aucune URL publique nécessaire).

## 4. Exposer la PWA

Le conteneur `web` écoute sur `127.0.0.1:8080` et relaie `/api/` vers le backend. Trois options :

**Traefik (n8n Hostinger)** : décommenter les `labels` et le réseau `n8n_default` dans
`docker-compose.yml`, adapter le `Host(...)` et le nom du certresolver (voir le compose de n8n), puis
`docker compose up -d`.

**Caddy** :

```
edgebet.mondomaine.fr {
    reverse_proxy 127.0.0.1:8080
}
```

**Nginx** :

```
server {
    server_name edgebet.mondomaine.fr;
    location / { proxy_pass http://127.0.0.1:8080; proxy_set_header Host $host; }
}
```
puis `certbot --nginx -d edgebet.mondomaine.fr`.

Sur le téléphone : ouvrir l'URL, « Ajouter à l'écran d'accueil », puis dans ⚙️ saisir la clé API
(`EDGEBET_API_KEY`) pour pouvoir marquer les paris joués.

## 5. n8n (optionnel)

Le worker interne suffit. Si tu préfères piloter depuis n8n : importer `n8n/workflow_edgebet_grille.json`,
remplacer `REMPLACER_PAR_EDGEBET_API_KEY`, le jeton et le chat Telegram, et mettre n8n sur le même réseau
Docker que `edgebet-api` (ou exposer `127.0.0.1:8000:8000` et appeler `http://host.docker.internal:8000`).
Dans ce cas, désactiver la planification interne en retirant le service `worker` du compose, ou en le
laissant uniquement pour l'écoute Telegram (il ne double pas la grille : une recommandation déjà en
attente pour le même match est mise à jour, pas dupliquée).

## 6. Exploitation

* **Mise à jour** : `git pull && cd deploy && docker compose --env-file .env up -d --build`.
* **Ré-entraînement** mensuel : `docker compose exec api edgebet train` (ou un second workflow n8n).
* **Sauvegarde** du volume (SQLite, modèles, CSV) :
  `docker run --rm -v edgebet-data:/data -v "$PWD":/backup alpine tar czf /backup/edgebet-data.tgz /data`.
* **Logs** : `docker compose logs -f worker`.
* **Équipes non reconnues** : le pipeline les signale (Telegram + logs) ; ajouter l'alias dans
  `backend/edgebet/sports/football/teams.yaml` et redéployer.
* **Quota The Odds API** : visible dans `GET /api/runs` et dans l'en-tête de la grille PWA.
