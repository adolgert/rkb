"""Pytest configuration for unit tests.

Unit tests must never make live network/LLM calls. A real ``GEMINI_API_KEY``
(or similar) leaking in from the developer's shell or ``local.env`` has caused
tests to accidentally hit a live API. Scrub those keys for every unit test so a
missing mock fails closed (empty result) instead of calling out.
"""

import pytest

_SCRUBBED_ENV_VARS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL_NAME",
    "ANTHROPIC_API_KEY",
    "S2_API_KEY",
)


@pytest.fixture(autouse=True)
def _scrub_live_api_keys(monkeypatch):
    """Remove LLM/registrar API keys from the environment for unit tests."""
    for name in _SCRUBBED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
