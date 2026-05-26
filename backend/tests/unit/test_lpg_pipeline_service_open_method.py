from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.integrations.playwright.lpg_consulta_client import LpgConsultaResult
from app.services.lpg_playwright_pipeline import (
    LpgPlaywrightPipelineService,
    TaxpayerPipelineResult,
    _taxpayer_result_to_dict,
)


def test_taxpayer_pipeline_result_defaults_service_open_method_to_none() -> None:
    result = TaxpayerPipelineResult(
        taxpayer_id=1,
        empresa="ACME SRL",
        cuit="20111111112",
        cuit_representado="20111111112",
    )

    assert result.service_open_method is None


def test_taxpayer_pipeline_result_serializes_service_open_method() -> None:
    result = TaxpayerPipelineResult(
        taxpayer_id=1,
        empresa="ACME SRL",
        cuit="20111111112",
        cuit_representado="20111111112",
    )
    result.service_open_method = "direct_url"

    payload = _taxpayer_result_to_dict(result)

    assert payload["service_open_method"] == "direct_url"


def test_process_taxpayer_propagates_service_open_method(monkeypatch: pytest.MonkeyPatch) -> None:
    """_process_taxpayer must copy client._service_open_method to the result after a successful run."""

    # --- Fake taxpayer (no DB needed) ---
    taxpayer = SimpleNamespace(
        id=42,
        empresa="ACME SRL",
        cuit="20111111112",
        cuit_representado="20222222223",
        activo=True,
        playwright_enabled=True,
    )

    # --- Fake LpgConsultaResult with no COEs so the loop is skipped ---
    fake_consulta = LpgConsultaResult(
        started_at="2024-01-01T00:00:00",
        finished_at="2024-01-01T00:01:00",
        empresa="ACME SRL",
        fecha_desde="2024-01-01",
        fecha_hasta="2024-01-31",
        total_rows=0,
        total_coes=0,
        headers=[],
        coes=[],
    )

    service = LpgPlaywrightPipelineService()

    # Stub validation helpers so they succeed without DB/crypto access
    monkeypatch.setattr(service, "_resolve_clave_fiscal", lambda tp: "fake_clave")
    monkeypatch.setattr(service, "_validate_taxpayer_ws_config", lambda tp: None)
    monkeypatch.setattr(service, "_build_ws_client_for_taxpayer", lambda tp: MagicMock())

    # Stub ArcaLpgPlaywrightClient.run: return the fake consulta AND set _service_open_method
    # on the instance — this is what the production code copies after a successful run.
    from app.integrations.playwright import ArcaLpgPlaywrightClient

    def fake_run(self: ArcaLpgPlaywrightClient, request: object) -> LpgConsultaResult:
        self._service_open_method = "direct_url"
        return fake_consulta

    monkeypatch.setattr(ArcaLpgPlaywrightClient, "run", fake_run)

    result = service._process_taxpayer(
        taxpayer=taxpayer,  # type: ignore[arg-type]
        fecha_desde="2024-01-01",
        fecha_hasta="2024-01-31",
        headless=True,
        timeout_ms=30_000,
        type_delay_ms=0,
        slow_mo_ms=0,
        post_action_delay_ms=0,
        login_max_retries=1,
        humanize_delays=False,
        retry_max_attempts=1,
        retry_base_delay_ms=0,
        on_phase=None,
    )

    assert result.service_open_method == "direct_url"
