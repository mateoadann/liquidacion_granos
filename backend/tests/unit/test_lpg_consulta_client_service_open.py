from unittest.mock import MagicMock

from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient


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
