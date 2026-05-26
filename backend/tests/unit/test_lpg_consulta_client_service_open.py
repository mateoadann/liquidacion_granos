from app.integrations.playwright.lpg_consulta_client import ArcaLpgPlaywrightClient


def test_lpg_consulta_client_exposes_direct_url_constant() -> None:
    assert (
        ArcaLpgPlaywrightClient.LPG_DIRECT_URL
        == "https://serviciosjava2.afip.gob.ar/lpg/jsp/index.jsp"
    )


def test_lpg_consulta_client_initializes_service_open_method_to_none() -> None:
    client = ArcaLpgPlaywrightClient()

    assert client._service_open_method is None
