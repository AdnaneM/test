"""Classifieur 1N2 par gradient boosting (scikit-learn, gère les valeurs manquantes nativement)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from edgebet.schema import LEAGUE_CODE_INDEX

DEFAULT_PARAMS: dict = {
    "loss": "log_loss",
    "learning_rate": 0.04,
    "max_iter": 350,
    "max_leaf_nodes": 12,
    "min_samples_leaf": 60,
    "l2_regularization": 2.0,
    "max_features": 0.8,
    "early_stopping": False,
    "random_state": 42,
}


@dataclass
class GBMModel:
    features: list[str]
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    model: HistGradientBoostingClassifier | None = None
    classes_: np.ndarray | None = None

    def _matrix(self, df: pd.DataFrame) -> np.ndarray:
        X = df.reindex(columns=self.features).copy()
        if "league_code" in X.columns:
            X["league_code"] = X["league_code"].fillna(-1)
        return X.to_numpy(dtype=float)

    def fit(self, df: pd.DataFrame, y: np.ndarray) -> GBMModel:
        cat_mask = [f == "league_code" for f in self.features]
        params = dict(self.params)
        if any(cat_mask):
            params["categorical_features"] = cat_mask
        self.model = HistGradientBoostingClassifier(**params)
        self.model.fit(self._matrix(df), y)
        self.classes_ = self.model.classes_
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Modèle non entraîné")
        raw = self.model.predict_proba(self._matrix(df))
        out = np.zeros((len(df), 3))
        for j, c in enumerate(self.classes_):
            out[:, int(c)] = raw[:, j]
        return out


def league_code_series(df: pd.DataFrame) -> pd.Series:
    return df["league"].map(LEAGUE_CODE_INDEX).astype(float)
