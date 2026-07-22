from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import r2_score


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ATTRIBUTION_PATH = ARTIFACT_DIR / "attribution_model.pkl"
FEATURES = [
    "traffic_density_index",
    "construction_permit_count",
    "industrial_stack_count",
    "thermal_anomaly_count_24h",
]


@dataclass
class AttributionModel:
    coefficients: dict[str, float]
    intercept: float
    confidence_score: float
    method: str = "nnls_regression"

    def predict_breakdown(self, frame: pd.DataFrame) -> dict[str, float]:
        row = frame[FEATURES].iloc[-1].fillna(0.0).astype(float).to_numpy()
        contributions = np.clip(row * np.array([self.coefficients[name] for name in FEATURES]), 0.0, None)
        total = float(contributions.sum()) or 1.0
        return {
            "traffic": round(float(contributions[0] / total * 100.0), 2),
            "construction": round(float(contributions[1] / total * 100.0), 2),
            "industrial": round(float(contributions[2] / total * 100.0), 2),
            "other": round(float(max(0.0, 100.0 - (contributions[:3].sum() / total * 100.0))), 2),
        }


def fit_attribution_model(master_table: pd.DataFrame) -> AttributionModel:
    frame = master_table.copy()
    frame = frame.sort_values(["ward_id", "timestamp"]).dropna(subset=["aqi"] + FEATURES)
    X = frame[FEATURES].astype(float).to_numpy()
    y = frame["aqi"].astype(float).to_numpy()
    if len(frame) < 8:
        coefficients = {feature: 0.0 for feature in FEATURES}
        confidence_score = 0.0
        intercept = float(np.mean(y) if len(y) else 0.0)
    else:
        coeffs, _ = nnls(X, y)
        coefficients = dict(zip(FEATURES, coeffs))
        intercept = float(np.clip(np.mean(y - X.dot(coeffs)), 0.0, None))
        confidence_score = float(max(r2_score(y, X.dot(coeffs) + intercept), 0.0))
    _ensure_artifacts_dir()
    model = AttributionModel(coefficients=coefficients, intercept=intercept, confidence_score=confidence_score)
    with ATTRIBUTION_PATH.open("wb") as handle:
        pickle.dump(model, handle)
    return model


def load_attribution_model(path: Path | None = None) -> AttributionModel:
    model_path = path or ATTRIBUTION_PATH
    with model_path.open("rb") as handle:
        return pickle.load(handle)


def _ensure_artifacts_dir() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def summarize_attribution(master_table: pd.DataFrame, ward_id: str) -> dict[str, object]:
    ward_frame = master_table.loc[master_table["ward_id"].astype(str) == str(ward_id)].copy()
    if ward_frame.empty:
        raise ValueError(f"No data for ward_id={ward_id}")
    model = fit_attribution_model(ward_frame)
    breakdown = model.predict_breakdown(ward_frame)
    return {
        "ward_id": ward_id,
        "timestamp": str(pd.Timestamp.utcnow()),
        "breakdown": breakdown,
        "confidence_score": round(model.confidence_score, 3),
        "method": model.method,
    }
