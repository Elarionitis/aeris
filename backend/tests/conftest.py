"""Shared test fixtures.

Every test writes its model artifacts and advisory cache into a temporary
directory. Without this, a test that trains a model on a small fixture
overwrites the real artifact in app/models/artifacts, and the running service
then serves predictions from that fixture.
"""

from __future__ import annotations

import pytest

from app.models import advisory as advisory_module
from app.models import attribution as attribution_module
from app.models import bootstrap as bootstrap_module
from app.models import forecasting as forecasting_module


@pytest.fixture(scope="session", autouse=True)
def isolated_artifacts(tmp_path_factory):
    """Redirect all artifact writes away from the repository."""
    root = tmp_path_factory.mktemp("artifacts")
    patch = pytest.MonkeyPatch()

    patch.setattr(forecasting_module, "ARTIFACT_DIR", root)
    patch.setattr(forecasting_module, "MODEL_PATH", root / "forecast_model.pkl")
    patch.setattr(attribution_module, "ARTIFACT_DIR", root)
    patch.setattr(attribution_module, "ATTRIBUTION_PATH", root / "attribution_model.pkl")
    patch.setattr(advisory_module, "ADVISORY_CACHE_DIR", root / "advisory_cache")

    yield root

    patch.undo()
    # Drop the process-wide caches so nothing leaks into a later session.
    bootstrap_module._CACHE.clear()
