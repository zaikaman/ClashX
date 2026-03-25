from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_ROOT = ROOT / "tests"
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: requires explicit Pacifica live credentials and opt-in")
    config.addinivalue_line("markers", "smoke: lightweight end-to-end contract or live smoke checks")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    live_enabled = os.getenv("PACIFICA_SMOKE_ENABLED") == "1"
    if live_enabled:
        return
    skip_live = pytest.mark.skip(reason="set PACIFICA_SMOKE_ENABLED=1 to run Pacifica live smoke tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
