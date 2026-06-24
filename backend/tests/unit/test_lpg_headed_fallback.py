from __future__ import annotations

import pytest


def test_launch_headed_cae_a_headless_si_falla(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()

    chromium = mocker.MagicMock()
    browser_ok = mocker.MagicMock()
    browser_ok.version = "120.0.0.0"
    # Primera llamada (headed) revienta; segunda (headless) OK.
    chromium.launch.side_effect = [RuntimeError("Xvfb no disponible"), browser_ok]

    result = client._launch_browser_with_fallback(
        chromium, headless=False, slow_mo_ms=0
    )

    assert result is browser_ok
    assert chromium.launch.call_count == 2
    # Segunda llamada fue headless=True
    assert chromium.launch.call_args_list[1].kwargs["headless"] is True


def test_launch_headed_ok_no_reintenta(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()
    chromium = mocker.MagicMock()
    browser_ok = mocker.MagicMock()
    chromium.launch.return_value = browser_ok

    result = client._launch_browser_with_fallback(
        chromium, headless=False, slow_mo_ms=0
    )

    assert result is browser_ok
    assert chromium.launch.call_count == 1
