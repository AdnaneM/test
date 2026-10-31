"""Artefact de modèle entraîné : GBM + température + poids du mélange + configuration des features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import joblib

from edgebet.models.gbm import GBMModel


@dataclass
class ModelBundle:
    gbm: GBMModel
    features: list[str]
    temperature: float
    weights: dict[str, float]
    feature_config: dict
    seasons: list[str]
    trained_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    metrics: dict = field(default_factory=dict)
    version: str = "0.1.0"

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: Path) -> ModelBundle:
        return joblib.load(Path(path))
