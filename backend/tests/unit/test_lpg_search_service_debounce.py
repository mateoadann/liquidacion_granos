from __future__ import annotations

import os

import pytest


def test_open_lpg_service_pauses_after_typing(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()

    login_page = mocker.MagicMock()
    search = mocker.MagicMock()
    login_page.get_by_role.return_value = search

    mocker.patch.object(client, "_click_dropdown_suggestion", return_value=True)
    mocker.patch.object(
        client,
        "_wait_for_lpg_service_link",
        return_value=(mocker.MagicMock(), "Liquidación primaria de granos"),
    )
    service_page = mocker.MagicMock()
    mocker.patch.object(client, "_open_service_popup", return_value=service_page)
    mocker.patch.object(client, "_wait_for_service_page_ready")
    post_action_pause = mocker.patch.object(client, "_post_action_pause")

    client._open_lpg_service(
        login_page=login_page,
        timeout_ms=30_000,
        type_delay_ms=80,
        empresa="ACME",
        humanize_delays=True,
    )

    debounce_calls = [
        call for call in post_action_pause.call_args_list
        if call.args[2] == "search_typed"
    ]
    assert len(debounce_calls) == 1
    call = debounce_calls[0]
    assert call.args[1] == 800
    assert call.args[3] == "ACME"
    assert call.args[4] is True


def test_open_lpg_service_propagates_humanize_disabled(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    client = ArcaLpgPlaywrightClient()

    login_page = mocker.MagicMock()
    login_page.get_by_role.return_value = mocker.MagicMock()
    mocker.patch.object(client, "_click_dropdown_suggestion", return_value=True)
    mocker.patch.object(
        client,
        "_wait_for_lpg_service_link",
        return_value=(mocker.MagicMock(), "link"),
    )
    mocker.patch.object(client, "_open_service_popup", return_value=mocker.MagicMock())
    mocker.patch.object(client, "_wait_for_service_page_ready")
    post_action_pause = mocker.patch.object(client, "_post_action_pause")

    client._open_lpg_service(
        login_page=login_page,
        timeout_ms=30_000,
        type_delay_ms=80,
        empresa="ACME",
        humanize_delays=False,
    )

    debounce_calls = [
        call for call in post_action_pause.call_args_list
        if call.args[2] == "search_typed"
    ]
    assert len(debounce_calls) == 1
    assert debounce_calls[0].args[4] is False


def test_wait_for_lpg_service_link_runs_diagnostics_before_raising(mocker):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
        PlaywrightFlowError,
    )
    from app.services.extraction_phases import ExtractionPhase

    client = ArcaLpgPlaywrightClient()

    login_page = mocker.MagicMock()
    locator = mocker.MagicMock()
    locator.count.return_value = 0
    login_page.locator.return_value = locator
    login_page.get_by_role.return_value = locator
    login_page.wait_for_timeout = mocker.MagicMock()

    mocker.patch("time.monotonic", side_effect=[0.0, 100.0])
    mocker.patch.object(client, "_detect_visible_service_links", return_value=["X"])
    diag = mocker.patch.object(client, "_log_search_service_diagnostics")

    client._search_dropdown_clicked = False
    with pytest.raises(PlaywrightFlowError) as excinfo:
        client._wait_for_lpg_service_link(login_page, timeout_ms=1)

    assert excinfo.value.phase == ExtractionPhase.SEARCH_SERVICE
    assert excinfo.value.dropdown_clicked is False
    diag.assert_called_once()
    assert diag.call_args.args[1] == ["X"]


def test_log_search_service_diagnostics_writes_screenshot_to_configured_path(
    mocker, tmp_path, monkeypatch
):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    monkeypatch.setenv("PLAYWRIGHT_DEBUG_PATH", str(tmp_path))

    client = ArcaLpgPlaywrightClient()
    client._search_dropdown_clicked = True

    login_page = mocker.MagicMock()
    search_locator = mocker.MagicMock()
    search_locator.count.return_value = 1
    search_locator.first.input_value.return_value = "liquidacion primaria de granos"
    login_page.get_by_role.return_value = search_locator

    empty_locator = mocker.MagicMock()
    empty_locator.count.return_value = 0
    login_page.locator.return_value = empty_locator
    login_page.url = "https://portalcf.cloud.afip.gob.ar/portal/app"
    body_locator = mocker.MagicMock()
    body_locator.inner_text.return_value = "Buscador AFIP"

    def locator_side_effect(selector, **_kwargs):
        if selector == "body":
            return body_locator
        return empty_locator

    login_page.locator.side_effect = locator_side_effect

    def fake_screenshot(path: str, full_page: bool):
        # Simula que Playwright crea el archivo
        with open(path, "wb") as fh:
            fh.write(b"PNG")

    login_page.screenshot.side_effect = fake_screenshot

    client._log_search_service_diagnostics(login_page, visible_services=["LPG"])

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("search_service_fail_")
    assert files[0].name.endswith(".png")


def test_log_search_service_diagnostics_swallows_screenshot_errors(
    mocker, tmp_path, monkeypatch
):
    from app.integrations.playwright.lpg_consulta_client import (
        ArcaLpgPlaywrightClient,
    )

    monkeypatch.setenv("PLAYWRIGHT_DEBUG_PATH", str(tmp_path))

    client = ArcaLpgPlaywrightClient()
    client._search_dropdown_clicked = False

    login_page = mocker.MagicMock()
    empty_locator = mocker.MagicMock()
    empty_locator.count.return_value = 0
    login_page.get_by_role.return_value = empty_locator
    login_page.locator.return_value = empty_locator
    login_page.url = ""
    login_page.screenshot.side_effect = RuntimeError("disk full")

    # No debe propagar la excepción del screenshot
    client._log_search_service_diagnostics(login_page, visible_services=[])
