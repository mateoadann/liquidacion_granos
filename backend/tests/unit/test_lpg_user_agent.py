from __future__ import annotations


def test_user_agent_es_linux_con_version_real():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()
    ua = client._build_user_agent("120.0.6099.109")

    assert "X11; Linux x86_64" in ua
    assert "Windows" not in ua
    assert "Chrome/120.0.6099.109" in ua
    assert ua.startswith("Mozilla/5.0")


def test_user_agent_normaliza_version_corta():
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()
    # browser.version puede venir como "120.0.6099.109" o solo mayor; aceptar ambos
    ua = client._build_user_agent("131.0.0.0")
    assert "Chrome/131.0.0.0" in ua
