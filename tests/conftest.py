"""Shared pytest configuration for offline unit and artifact integration tests."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    del config
    integration_items = [item for item in items if "integration" in item.keywords]
    if not integration_items:
        return

    from scripts.artifacts import all_artifacts_ready, inspect_artifacts

    checks = inspect_artifacts()
    if all_artifacts_ready(checks):
        return
    missing = ", ".join(check.name for check in checks if not check.ready)
    marker = pytest.mark.skip(
        reason=(
            f"integration artifacts unavailable ({missing}); run "
            ".venv/bin/python scripts/artifacts.py for recovery instructions"
        )
    )
    for item in integration_items:
        item.add_marker(marker)
