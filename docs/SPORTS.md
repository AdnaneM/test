# Sports : proposition et feuille de route

Le cœur d'EdgeBet est indépendant du sport : cotes, retrait de marge, détection de value bets, mise de
Kelly, score de risque, backtest, base, API, Telegram et PWA ne connaissent que des « événements à
issues ». Seuls les *adaptateurs* (sources de données, features, modèle de probabilités) sont propres à
chaque sport et vivent dans `backend/edgebet/sports/<sport>/`.

## Classement recommandé

| # | Sport | Données gratuites pour le backtest | Modèle | Volume de matchs | Efficacité des cotes FR | Verdict |
|---|-------|------------------------------------|--------|------------------|-------------------------|---------|
| 1 | **Football** (L1, L2, PL, Liga, Bundesliga, Serie A) | football-data.co.uk : 25 saisons avec cotes d'ouverture et de clôture Pinnacle ; ClubElo ; xG Understat/FBref | Dixon-Coles + gradient boosting + marché | Élevé le week-end, faible en semaine | Très élevée sur les gros championnats, moindre en Ligue 2 et sur les totaux | **Phase 0, en place** |
| 2 | **Tennis** (ATP, WTA, Challengers) | Dépôts Jeff Sackmann (tous les matchs depuis 1968, stats service/retour) ; tennis-data.co.uk (cotes Bet365/Pinnacle depuis 2001) | Elo par surface + stats service/retour + fatigue (matchs des 7 derniers jours) | **Très élevé, toute l'année, tous les jours** | Moyenne hors Grand Chelem, faible sur les Challengers | **Phase 3, meilleur second sport** |
| 3 | **Basket** (NBA, Euroligue, Betclic Élite) | NBA : stats officielles via API non documentée + Basketball-Reference ; Euroligue : site officiel | Elo (type FiveThirtyEight) + four factors + repos (back-to-back très prédictif) + blessés | Élevé d'octobre à juin, quotidien | Élevée en NBA (marché US liquide), moyenne en Europe | Phase 4 |
| 4 | **Rugby** (Top 14, Pro D2, Six Nations) | Peu de sources structurées gratuites ; scraping nécessaire | Elo + Poisson sur les points | Faible (un week-end sur deux) | Faible : marché franco-français peu arbitré | Intéressant pour l'edge, coûteux en données |
| 5 | **Hockey** (NHL) | API NHL publique | Poisson à faible score, gardiens | Élevé | Élevée | Possible, peu d'intérêt pour un parieur français |
| 6 | Handball, volley | Quasi inexistantes | — | Faible | Faible | Déconseillé : pas de quoi backtester |
| — | Courses hippiques (PMU) | Pari mutuel : logique totalement différente | — | — | — | Hors périmètre |
| — | Esport | Données fragmentées | — | — | — | Hors périmètre |

## Pourquoi commencer par le football

* La seule source gratuite qui fournit **des cotes de clôture historiques** (football-data.co.uk), ce qui
  permet de mesurer honnêtement le CLV et de savoir si le modèle a une vraie edge avant de miser.
* Winamax, Unibet et Betclic sont couverts par The Odds API pour les six championnats configurés.
* Les features riches (Elo, forme, tirs cadrés, xG, blessés) ont du sens et sont documentées dans la
  littérature (Dixon & Coles 1997, Constantinou, Koopman & Lit...).

## Pourquoi le tennis est le meilleur deuxième sport

* Des matchs **tous les jours** de janvier à novembre : la grille quotidienne a toujours de la matière.
* Deux issues seulement, pas de nul : la détection de value est plus stable.
* Les Challengers et le circuit WTA secondaire sont moins bien cotés par les bookmakers français que les
  gros championnats de football ; les modèles Elo par surface y sont réputés compétitifs.
* Les données Sackmann sont complètes et gratuites ; tennis-data.co.uk donne les cotes historiques.
* Points d'attention : abandons et forfaits (prévoir le marché « vainqueur, mise remboursée si abandon »
  selon le bookmaker), et les limitations de compte plus fréquentes sur le tennis.

## Ce qu'il faudrait ajouter pour un nouveau sport

1. `sports/<sport>/loader.py` : historique au schéma canonique (`match_id, date, home, away, result`
   et cotes `odds_<book>_*`), même pour deux issues (colonne `d` à NaN).
2. `sports/<sport>/features.py` : Elo adapté, forme, repos, surface, etc.
3. Un modèle de probabilités (Elo logistique ou GBM) branché dans `build_feature_frame`.
4. Les clés The Odds API des compétitions (`tennis_atp_*`, `basketball_nba`, `basketball_euroleague`,
   `rugbyunion_*`...), et les alias de noms.
5. Le backtest existant fonctionne tel quel une fois ces colonnes fournies.
