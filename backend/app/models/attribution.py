"""Source attribution agent.

Fits a non-negative least squares model of AQI against four source-activity
signals, then converts the fitted contributions into a percentage breakdown.
Non-negativity is what makes the coefficients physically interpretable: no
source is allowed to "clean" the air.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from sklearn.metrics import r2_score

from app.core.logging import get_logger

logger = get_logger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ATTRIBUTION_PATH = ARTIFACT_DIR / "attribution_model.pkl"

FEATURES = [
    "traffic_density_index",
    "construction_permit_count",
    "industrial_stack_count",
    "thermal_anomaly_count_24h",
]
#: Minimum rows needed before the regression is trusted over the mean.
MIN_TRAINING_ROWS = 8

__all__ = [
    "ATTRIBUTION_PATH",
    "FEATURES",
    "AttributionModel",
    "fit_attribution_model",
    "load_attribution_model",
    "summarize_attribution",
]


@dataclass
class AttributionModel:
    """Fitted NNLS attribution model."""

    coefficients: dict[str, float]
    intercept: float
    confidence_score: float
    method: str = "nnls_regression"
    trained_rows: int = 0
    feature_names: list[str] = field(default_factory=lambda: list(FEATURES))

    def predict_breakdown(self, frame: pd.DataFrame) -> dict[str, float]:
        """Percentage contribution of each source for the latest row of ``frame``.

        ``other`` absorbs both the fitted intercept (regional background) and
        thermal anomalies such as open waste burning. The four values always
        sum to 100.
        """
        missing = [name for name in FEATURES if name not in frame.columns]
        if missing:
            raise KeyError(f"Attribution input is missing features: {', '.join(missing)}")
        if frame.empty:
            raise ValueError("Attribution input frame is empty")

        row = frame[FEATURES].iloc[-1].fillna(0.0).astype(float).to_numpy()
        coefficients = np.array([float(self.coefficients.get(name, 0.0)) for name in FEATURES])
        contributions = np.clip(row * coefficients, 0.0, None)
        background = max(float(self.intercept), 0.0)

        total = float(contributions.sum()) + background
        if total <= 0.0:
            # Nothing to attribute: report it as unexplained rather than guessing.
            return {"traffic": 0.0, "construction": 0.0, "industrial": 0.0, "other": 100.0}

        shares = {
            "traffic": contributions[0] / total * 100.0,
            "construction": contributions[1] / total * 100.0,
            "industrial": contributions[2] / total * 100.0,
            "other": (contributions[3] + background) / total * 100.0,
        }
        rounded = {name: round(float(value), 2) for name, value in shares.items()}
        # Push any rounding residue into "other" so the chart always totals 100.
        rounded["other"] = round(100.0 - sum(v for k, v in rounded.items() if k != "other"), 2)
        return rounded


def _ensure_artifacts_dir() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def fit_attribution_model(master_table: pd.DataFrame, persist: bool = True) -> AttributionModel:
    """Fit the NNLS model and (by default) persist it to the artifact directory."""
    frame = master_table.copy()
    sort_columns = [column for column in ("ward_id", "timestamp") if column in frame.columns]
    if sort_columns:
        frame = frame.sort_values(sort_columns)
    frame = frame.dropna(subset=["aqi"] + FEATURES)

    features = frame[FEATURES].astype(float).to_numpy()
    target = frame["aqi"].astype(float).to_numpy()

    if len(frame) < MIN_TRAINING_ROWS:
        logger.warning(
            "Attribution fitted on %d rows (<%d); falling back to mean-only model",
            len(frame), MIN_TRAINING_ROWS,
        )
        model = AttributionModel(
            coefficients={name: 0.0 for name in FEATURES},
            intercept=float(np.mean(target)) if len(target) else 0.0,
            confidence_score=0.0,
            trained_rows=len(frame),
        )
    else:
        coefficients, _ = nnls(features, target)
        residual = target - features.dot(coefficients)
        intercept = float(np.clip(np.mean(residual), 0.0, None))
        fitted = features.dot(coefficients) + intercept
        model = AttributionModel(
            coefficients=dict(zip(FEATURES, (float(value) for value in coefficients))),
            intercept=intercept,
            confidence_score=float(np.clip(r2_score(target, fitted), 0.0, 1.0)),
            trained_rows=len(frame),
        )

    if persist:
        _ensure_artifacts_dir()
        with ATTRIBUTION_PATH.open("wb") as handle:
            pickle.dump(model, handle)
        logger.info(
            "Attribution model saved (rows=%d, r2=%.3f)", model.trained_rows, model.confidence_score
        )
    return model


def load_attribution_model(path: Path | None = None) -> AttributionModel:
    """Load the persisted model, raising ``FileNotFoundError`` if absent."""
    model_path = path or ATTRIBUTION_PATH
    with model_path.open("rb") as handle:
        model = pickle.load(handle)
    if not isinstance(model, AttributionModel):
        raise ValueError(f"Unexpected attribution artifact type: {type(model).__name__}")
    return model


def summarize_attribution(master_table: pd.DataFrame, ward_id: str) -> dict[str, object]:
    """Fit on a single ward's history and return its breakdown."""
    ward_frame = master_table.loc[master_table["ward_id"].astype(str) == str(ward_id)].copy()
    if ward_frame.empty:
        raise ValueError(f"No data for ward_id={ward_id}")
    model = fit_attribution_model(ward_frame)
    return {
        "ward_id": str(ward_id),
        "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "breakdown": model.predict_breakdown(ward_frame),
        "confidence_score": round(model.confidence_score, 3),
        "method": model.method,
    }
