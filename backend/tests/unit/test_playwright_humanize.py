from __future__ import annotations

import pytest


def test_humanized_delay_returns_value_within_range():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()
    base_ms = 1000
    variance = 0.3

    results = [client._humanized_delay(base_ms, variance) for _ in range(100)]

    min_expected = int(base_ms * (1 - variance))  # 700
    max_expected = int(base_ms * (1 + variance))  # 1300

    assert all(min_expected <= r <= max_expected for r in results)
    assert len(set(results)) > 1  # Verificar que hay variación


def test_humanized_delay_with_zero_variance_returns_base():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    result = client._humanized_delay(500, variance_percent=0.0)

    assert result == 500


def test_humanized_delay_disabled_returns_base():
    from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient

    client = ArcaLpgPlaywrightClient()

    result = client._humanized_delay(500, variance_percent=0.3, enabled=False)

    assert result == 500
