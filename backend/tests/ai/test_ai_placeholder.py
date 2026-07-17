"""Placeholder for the AI test suite (populated in Phases 4-8)."""

from __future__ import annotations

import importlib


def test_ai_package_importable():
    # The AI subsystem is intentionally empty in Phase 1; just ensure the
    # package imports so the test path exists and CI wiring is exercised.
    module = importlib.import_module("app.ai")
    assert module is not None
