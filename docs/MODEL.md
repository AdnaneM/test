# Méthodologie du modèle

## Idée directrice

On ne cherche pas à « prédire le football mieux que tout le monde ». On cherche des cotes de
bookmakers français **décalées** par rapport à la meilleure estimation disponible, construite en
mélangeant trois sources :

1. **Dixon-Coles** : Poisson bivarié sur les buts, avec correction des scores faibles (paramètre ρ),
   avantage du terrain et pondération temporelle exponentielle (`dc_xi` par jour, ré-ajustement tous les
   `dc_refit_days` jours sur une fenêtre de `dc_window_days`). Gradient analytique : un ajustement prend
   quelques dizaines de millisecondes. Fournit 1N2, plus/moins 2,5 buts, les deux équipes marquent.
2. **Gradient boosting** (scikit-learn `HistGradientBoostingClassifier`, trois classes) sur des
   régresseurs causaux :
   * Elo pré-match (K = 20, avantage du terrain 65 points, multiplicateur de marge de victoire),
     différence et espérance Elo ;
   * forme glissante sur 5 et 10 matchs : points, buts pour/contre, tirs, tirs cadrés, forme à domicile
     ou à l'extérieur, jours de repos, nombre de matchs joués dans la saison ;
   * probabilités Dixon-Coles (empilement) ;
   * probabilités implicites sans marge du bookmaker de référence (Pinnacle, cotes d'ouverture dans
     l'historique, cotes du matin en production) ;
   * championnat (catégoriel).
   Calibration par température ajustée sur une saison de validation.
3. **Marché** : probabilités Pinnacle sans marge (méthode `power` par défaut, `shin` ou
   `multiplicative` possibles).

Les trois sont combinées par un pool linéaire dont les poids minimisent la log-loss sur la saison de
validation. En pratique le marché prend un poids important : c'est attendu, et c'est honnête.

## Décision de mise

Pour chaque issue et chaque bookmaker configuré :

* `edge = p_modèle × cote − 1` ; on exige `edge ≥ EDGEBET_MIN_EDGE` (3 % par défaut) ;
* garde-fou Pinnacle : si la cote jouée implique une edge inférieure à `−EDGEBET_SHARP_TOLERANCE` face
  aux probabilités Pinnacle, on ne parie pas contre le marché de référence ;
* cotes entre `MIN_ODDS` et `MAX_ODDS`, probabilité ≥ `MIN_PROBABILITY` ;
* mise = Kelly × `KELLY_FRACTION` (¼ par défaut), plafonnée à `MAX_STAKE_FRACTION` de la bankroll
  courante, arrondie à 0,50 € ;
* au plus un pari par match, `MAX_BETS_PER_DAY` par jour, classés par edge.

**Score de risque (1 à 5)** : niveau de cote (1 sous 1,60 … 5 au-dessus de 5,00), +1 si les trois
sources divergent fortement (écart-type > 0,08), +1 si les équipes ont moins de cinq matchs dans la saison.

## Protocole d'évaluation (backtest)

Walk-forward strict, saison par saison : entraînement sur les saisons antérieures, calibration et poids
sur la saison précédente, test sur la saison cible. Toutes les features sont calculées avec `shift(1)`
ou un ajustement « avant la date du jour » ; un test automatique vérifie qu'altérer les résultats futurs
ne change aucune feature passée.

Indicateurs à lire dans l'ordre :

1. **Log-loss / Brier** du mélange face au marché d'ouverture et de clôture. Si `final` n'est pas sous
   `market_open`, le modèle n'apporte rien.
2. **CLV moyen** des paris simulés face à la clôture Pinnacle. C'est le meilleur prédicteur d'une edge
   durable ; un ROI positif sur quelques centaines de paris ne prouve rien.
3. **ROI** à mise fixe et en Kelly fractionné, drawdown maximal, par saison, ligue et niveau de risque.

Cotes utilisées : `avg` (moyenne du marché) est réaliste pour un parieur français ; `max` surestime.
Les cotes Winamax/Unibet ne sont pas dans l'historique : en production, le règlement enregistre la cote
réellement jouée et le CLV réel.

## Limites connues et évolutions

* Blessés, compositions, valeur marchande, xG ne sont pas encore dans le modèle (pas d'historique
  gratuit fiable pour les backtester) : API-Football est branché et pourra alimenter le score de risque
  puis des features une fois un historique constitué.
* Marchés : seul 1N2 est joué ; Dixon-Coles fournit déjà plus/moins 2,5 et BTTS, à activer quand
  The Odds API `totals` sera consommé (coût en crédits ×2).
* Cross-championnat : Dixon-Coles est ajusté par ligue ; les promus héritent d'une pénalité moyenne.
