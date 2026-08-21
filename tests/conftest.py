"""Shared pytest configuration for offline unit and artifact integration tests."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    del config
    integration_items = [item for item in items if "integration" in item.keywords]
    if not integration_items:
        return

    from scripts.artifacts import inspect_artifacts

    checks = inspect_artifacts()
    by_name = {check.name: check for check in checks}
    for item in integration_items:
        requirement = item.get_closest_marker("requires_artifacts")
        required_names = tuple(requirement.args) if requirement else tuple(by_name)
        missing = [
            name
            for name in required_names
            if name not in by_name or not by_name[name].ready
        ]
        if not missing:
            continue
        item.add_marker(
            pytest.mark.skip(
                reason=(
                    f"integration artifacts unavailable ({', '.join(missing)}); run "
                    ".venv/bin/python scripts/artifacts.py for recovery instructions"
                )
            )
        )
