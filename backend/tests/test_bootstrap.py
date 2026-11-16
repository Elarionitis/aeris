"""Tests for synthetic history generation and model bootstrapping."""

from __future__ import annotations

import pytest

from app.models.bootstrap import (
    HISTORY_HOURS,
    ensure_models,
    model_status,
    synthetic_master_table,
    ward_history,
)
from app.models.forecasting import FEATURE_COLUMNS, build_training_frame


def test_master_table_is_deterministic():
    first = synthetic_master_table(hours=72, seed=7)
    second = synthetic_master_table(hours=72, seed=7)
    assert first.equals(second)
    assert not first.equals(synthetic_master_table(hours=72, seed=8))


def test_master_table_covers_every_ward_hourly():
    table = synthetic_master_table(hours=96)
    counts = table.groupby("ward_id").size()
    assert counts.nunique() == 1
    assert counts.iloc[0] == 96
    assert table["aqi"].between(15, 480).all()
    assert not table.isna().any().any()


def test_master_table_supports_the_model_feature_set():
    frame = build_training_frame(synthetic_master_table(hours=HISTORY_HOURS))
    assert not frame.empty
    for column in FEATURE_COLUMNS:
        assert column in frame.columns
        assert frame[column].notna().all()


def test_history_is_autocorrelated():
    """Lag features are only useful if the series is not white noise."""
    table = synthetic_master_table(hours=HISTORY_HOURS)
    series = table.loc[table["ward_id"] == "BTM", "aqi"].reset_index(drop=True)
    assert series.autocorr(lag=1) > 0.5


def test_ward_history_returns_enough_rows_for_lags():
    history = ward_history("BTM", hours=48)
    assert len(history) == 48
    # Fewer than 25 rows would break the 24-hour lag feature.
    assert len(ward_history("BTM", hours=4)) >= 25


def test_ward_history_rejects_unknown_ward():
    with pytest.raises(KeyError):
        ward_history("Atlantis")


def test_ensure_models_is_idempotent_and_reports_status():
    first = ensure_models()
    assert first.ready, first.errors

    second = ensure_models()
    assert second.ready
    # Nothing is retrained once the artifacts exist.
    assert second.as_dict()["trained_this_startup"] == []
    assert model_status().ready
