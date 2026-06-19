from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.integrations.playwright.lpg_consulta_client import (
    ArcaLpgPlaywrightClient,
    ExtractionPhase,
    PlaywrightFlowError,
)


def test_lpg_consulta_client_exposes_direct_url_constant() -> None:
    assert (
        ArcaLpgPlaywrightClient.LPG_DIRECT_URL
        == "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    )


def test_lpg_consulta_client_initializes_service_open_method_to_none() -> None:
    client = ArcaLpgPlaywrightClient()

    assert client._service_open_method is None


def _build_client_with_stubbed_open_path(
    open_service_returns: object,
    wait_ready_returns: object | None = None,
    wait_ready_side_effect: BaseException | None = None,
) -> tuple[ArcaLpgPlaywrightClient, MagicMock]:
    client = ArcaLpgPlaywrightClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(
        return_value=(MagicMock(name="service_link"), "Liquidación primaria de granos")
    )
    client._open_service_popup = MagicMock(return_value=open_service_returns)
    if wait_ready_side_effect is not None:
        client._wait_for_service_page_ready = MagicMock(
            side_effect=wait_ready_side_effect
        )
    else:
        client._wait_for_service_page_ready = MagicMock(return_value=wait_ready_returns)

    login_page = MagicMock(name="login_page")
    search = MagicMock(name="search_combobox")
    login_page.get_by_role.return_value = search
    return client, login_page


def test_open_lpg_service_marks_method_search_box_on_happy_path() -> None:
    service_page = MagicMock(name="service_page")
    client, login_page = _build_client_with_stubbed_open_path(
        open_service_returns=service_page
    )

    result = client._open_lpg_service(
        login_page=login_page,
        timeout_ms=10_000,
        type_delay_ms=10,
        empresa="ACME SRL",
        humanize_delays=False,
    )

    assert result is service_page
    assert client._service_open_method == "search_box"
    login_page.context.new_page.assert_not_called()


def test_open_lpg_service_via_direct_url_navigates_and_validates() -> None:
    client = ArcaLpgPlaywrightClient()
    client._wait_for_service_page_ready = MagicMock()

    direct_page = MagicMock(name="direct_page")
    direct_page.url = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    context = MagicMock(name="context")
    context.new_page.return_value = direct_page
    login_page = MagicMock(name="login_page")
    login_page.context = context

    returned = client._open_lpg_service_via_direct_url(
        login_page, timeout_ms=10_000, empresa="ACME SRL"
    )

    assert returned is direct_page
    context.new_page.assert_called_once_with()
    direct_page.goto.assert_called_once_with(
        ArcaLpgPlaywrightClient.LPG_DIRECT_URL,
        wait_until="networkidle",
        timeout=60_000,  # default nav_login_timeout_ms
    )
    client._wait_for_service_page_ready.assert_called_once_with(
        direct_page, 10_000, "ACME SRL"
    )
    direct_page.close.assert_not_called()


def test_open_lpg_service_via_direct_url_closes_page_on_failure() -> None:
    client = ArcaLpgPlaywrightClient()
    failure = PlaywrightFlowError("not ready", phase=ExtractionPhase.OPEN_SERVICE)
    client._wait_for_service_page_ready = MagicMock(side_effect=failure)

    direct_page = MagicMock(name="direct_page")
    direct_page.url = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    context = MagicMock(name="context")
    context.new_page.return_value = direct_page
    login_page = MagicMock(name="login_page")
    login_page.context = context

    with pytest.raises(PlaywrightFlowError):
        client._open_lpg_service_via_direct_url(
            login_page, timeout_ms=10_000, empresa="ACME SRL"
        )

    direct_page.close.assert_called_once()


def test_open_lpg_service_falls_back_to_direct_url_on_search_service_error() -> None:
    client = ArcaLpgPlaywrightClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(
        side_effect=PlaywrightFlowError(
            "No se encontró el servicio",
            phase=ExtractionPhase.SEARCH_SERVICE,
            dropdown_clicked=True,
        )
    )

    direct_page = MagicMock(name="direct_page")
    direct_page.url = "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    context = MagicMock(name="context")
    context.new_page.return_value = direct_page

    login_page = MagicMock(name="login_page")
    login_page.context = context
    login_page.get_by_role.return_value = MagicMock(name="search_combobox")

    client._wait_for_service_page_ready = MagicMock()

    result = client._open_lpg_service(
        login_page=login_page,
        timeout_ms=10_000,
        type_delay_ms=10,
        empresa="ACME SRL",
        humanize_delays=False,
    )

    assert result is direct_page
    assert client._service_open_method == "direct_url"
    context.new_page.assert_called_once_with()
    direct_page.goto.assert_called_once_with(
        ArcaLpgPlaywrightClient.LPG_DIRECT_URL,
        wait_until="networkidle",
        timeout=60_000,  # default nav_login_timeout_ms
    )


def test_open_lpg_service_reraises_original_error_when_direct_url_also_fails() -> None:
    original = PlaywrightFlowError(
        "No se encontró el servicio",
        phase=ExtractionPhase.SEARCH_SERVICE,
        dropdown_clicked=True,
    )

    client = ArcaLpgPlaywrightClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(side_effect=original)
    client._open_lpg_service_via_direct_url = MagicMock(
        side_effect=PlaywrightFlowError(
            "direct url failed",
            phase=ExtractionPhase.OPEN_SERVICE,
        )
    )

    login_page = MagicMock(name="login_page")
    login_page.get_by_role.return_value = MagicMock(name="search_combobox")

    with pytest.raises(PlaywrightFlowError) as exc_info:
        client._open_lpg_service(
            login_page=login_page,
            timeout_ms=10_000,
            type_delay_ms=10,
            empresa="ACME SRL",
            humanize_delays=False,
        )

    raised = exc_info.value
    assert raised is original
    assert raised.phase == ExtractionPhase.SEARCH_SERVICE
    assert raised.dropdown_clicked is True
    client._open_lpg_service_via_direct_url.assert_called_once_with(
        login_page, 10_000, "ACME SRL", nav_login_timeout_ms=60_000
    )
    assert client._service_open_method is None


def test_open_lpg_service_does_not_fallback_on_open_service_phase() -> None:
    open_service_error = PlaywrightFlowError(
        "popup timed out",
        phase=ExtractionPhase.OPEN_SERVICE,
    )

    client = ArcaLpgPlaywrightClient()
    client._emit_phase = MagicMock()
    client._post_action_pause = MagicMock()
    client._click_dropdown_suggestion = MagicMock(return_value=True)
    client._wait_for_lpg_service_link = MagicMock(
        return_value=(MagicMock(name="service_link"), "Liquidación primaria de granos")
    )
    client._open_service_popup = MagicMock(side_effect=open_service_error)

    context = MagicMock(name="context")
    login_page = MagicMock(name="login_page")
    login_page.context = context
    login_page.get_by_role.return_value = MagicMock(name="search_combobox")

    # Also fail the existing retry path so the original OPEN_SERVICE error surfaces.
    exact_link = MagicMock(name="exact_link")
    exact_link.count.return_value = 0
    login_page.locator.return_value = exact_link

    with pytest.raises(PlaywrightFlowError) as exc_info:
        client._open_lpg_service(
            login_page=login_page,
            timeout_ms=10_000,
            type_delay_ms=10,
            empresa="ACME SRL",
            humanize_delays=False,
        )

    assert exc_info.value.phase == ExtractionPhase.OPEN_SERVICE
    context.new_page.assert_not_called()
    assert client._service_open_method is None
