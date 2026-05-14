from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.extensions import db
from app.integrations.playwright.lpg_consulta_client import LpgConsultaResult
from app.models.taxpayer import Taxpayer
from app.services.lpg_playwright_pipeline import LpgPlaywrightPipelineService


def _create_taxpayer() -> Taxpayer:
    tp = Taxpayer(
        cuit="20304050607",
        empresa="Test SA",
        cuit_representado="30711165378",
        clave_fiscal_encrypted="ignored",
        ambiente="homologacion",
    )
    tp.cert_crt_path = "/tmp/test.crt"
    tp.cert_key_path = "/tmp/test.key"
    db.session.add(tp)
    db.session.flush()
    return tp


def _build_consulta(coes_entries: list[dict[str, str]]) -> LpgConsultaResult:
    return LpgConsultaResult(
        started_at="2026-05-13T00:00:00",
        finished_at="2026-05-13T00:00:05",
        empresa="Test SA",
        fecha_desde="01/01/2026",
        fecha_hasta="26/02/2026",
        total_rows=len(coes_entries),
        total_coes=len(coes_entries),
        headers=["Coe", "Tipo operación"],
        coes=coes_entries,
    )


def _run_pipeline_for(
    taxpayer: Taxpayer,
    consulta: LpgConsultaResult,
    *,
    liquidacion_return=None,
    ajuste_return=None,
    liquidacion_side_effect=None,
    ajuste_side_effect=None,
):
    """Execute the pipeline COE loop with mocked Playwright + WS client.

    Returns a tuple (result, ws_client_mock).
    """
    service = LpgPlaywrightPipelineService()

    ws_client = MagicMock()
    if liquidacion_side_effect is not None:
        ws_client.call_liquidacion_x_coe.side_effect = liquidacion_side_effect
    else:
        ws_client.call_liquidacion_x_coe.return_value = (
            liquidacion_return or {"data": {"pdf": ""}}
        )
    if ajuste_side_effect is not None:
        ws_client.call_ajuste_x_coe.side_effect = ajuste_side_effect
    else:
        ws_client.call_ajuste_x_coe.return_value = (
            ajuste_return or {"data": {"pdf": ""}}
        )

    fake_playwright = MagicMock()
    fake_playwright.run.return_value = consulta

    with patch.object(service, "_resolve_clave_fiscal", return_value="clave"), patch.object(
        service, "_validate_taxpayer_ws_config", return_value=None
    ), patch.object(service, "_build_ws_client_for_taxpayer", return_value=ws_client), patch.object(
        service, "_coe_exists", return_value=False
    ), patch.object(service, "_save_lpg_document", return_value=None), patch(
        "app.services.lpg_playwright_pipeline.ArcaLpgPlaywrightClient",
        return_value=fake_playwright,
    ):
        result = service._process_taxpayer(
            taxpayer=taxpayer,
            fecha_desde="01/01/2026",
            fecha_hasta="26/02/2026",
            headless=True,
            timeout_ms=30000,
            type_delay_ms=80,
            slow_mo_ms=0,
            post_action_delay_ms=0,
            login_max_retries=1,
            humanize_delays=False,
            retry_max_attempts=1,
            retry_base_delay_ms=10,
            on_phase=None,
        )

    return result, ws_client


class TestAjusteHtmlPreDetection:
    def test_compraventa_liquidacion_calls_liquidacion_only(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            consulta = _build_consulta(
                [{"coe": "330130301001", "tipo_operacion": "Compraventa de granos"}]
            )
            result, ws_client = _run_pipeline_for(tp, consulta)

            assert ws_client.call_liquidacion_x_coe.call_count == 1
            assert ws_client.call_ajuste_x_coe.call_count == 0
            assert result.total_procesados_ok == 1
            assert result.total_procesados_error == 0

    def test_compraventa_ajuste_unificado_calls_ajuste_directly(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            consulta = _build_consulta(
                [
                    {
                        "coe": "330230403455",
                        "tipo_operacion": "Compraventa de granos - Ajuste Unificado",
                    }
                ]
            )
            result, ws_client = _run_pipeline_for(tp, consulta)

            assert ws_client.call_ajuste_x_coe.call_count == 1
            assert ws_client.call_liquidacion_x_coe.call_count == 0
            assert result.total_procesados_ok == 1
            assert result.total_procesados_error == 0

    def test_consignacion_ajuste_unificado_calls_ajuste_directly(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            consulta = _build_consulta(
                [
                    {
                        "coe": "330130301752",
                        "tipo_operacion": "Consignación de granos - Ajuste Unificado",
                    }
                ]
            )
            result, ws_client = _run_pipeline_for(tp, consulta)

            assert ws_client.call_ajuste_x_coe.call_count == 1
            assert ws_client.call_liquidacion_x_coe.call_count == 0
            assert result.total_procesados_ok == 1

    def test_compraventa_with_error_1861_falls_back_to_ajuste(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            consulta = _build_consulta(
                [{"coe": "330130389445", "tipo_operacion": "Compraventa de granos"}]
            )
            error_1861_payload = {
                "data": {
                    "errores": {
                        "error": [
                            {"codigo": "1861", "descripcion": "El COE es un ajuste"}
                        ]
                    }
                }
            }
            result, ws_client = _run_pipeline_for(
                tp,
                consulta,
                liquidacion_return=error_1861_payload,
                ajuste_return={"data": {"pdf": ""}},
            )

            assert ws_client.call_liquidacion_x_coe.call_count == 1
            assert ws_client.call_ajuste_x_coe.call_count == 1
            assert result.total_procesados_ok == 1
            assert result.total_procesados_error == 0

    def test_compraventa_with_parser_exception_falls_back_to_ajuste(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            consulta = _build_consulta(
                [{"coe": "330130389445", "tipo_operacion": "Compraventa de granos"}]
            )
            parser_exc = Exception(
                "Unexpected element 'ajusteCredito', expected 'codTipoOperacion'"
            )
            result, ws_client = _run_pipeline_for(
                tp,
                consulta,
                liquidacion_side_effect=parser_exc,
                ajuste_return={"data": {"pdf": ""}},
            )

            assert ws_client.call_liquidacion_x_coe.call_count == 1
            assert ws_client.call_ajuste_x_coe.call_count == 1
            assert result.total_procesados_ok == 1
            assert result.total_procesados_error == 0

    def test_ajuste_html_with_ws_exception_does_not_retry(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            consulta = _build_consulta(
                [
                    {
                        "coe": "330230403455",
                        "tipo_operacion": "Compraventa de granos - Ajuste Unificado",
                    }
                ]
            )
            parser_exc = Exception("Unexpected element 'ajusteCredito'")
            result, ws_client = _run_pipeline_for(
                tp,
                consulta,
                ajuste_side_effect=parser_exc,
            )

            # Already in the ajuste path: no fallback to liquidacion.
            assert ws_client.call_ajuste_x_coe.call_count == 1
            assert ws_client.call_liquidacion_x_coe.call_count == 0
            assert result.total_procesados_ok == 0
            assert result.total_procesados_error == 1
            assert result.coes_error[0]["coe"] == "330230403455"

    def test_missing_tipo_operacion_defaults_to_liquidacion_path(self, app):
        with app.app_context():
            tp = _create_taxpayer()
            # Older HTML without "Tipo operación" column: tipo_operacion is "".
            consulta = _build_consulta(
                [{"coe": "330130389999", "tipo_operacion": ""}]
            )
            error_1861_payload = {
                "data": {
                    "errores": {
                        "error": [{"codigo": "1861", "descripcion": "ajuste"}]
                    }
                }
            }
            result, ws_client = _run_pipeline_for(
                tp,
                consulta,
                liquidacion_return=error_1861_payload,
                ajuste_return={"data": {"pdf": ""}},
            )

            # Default = liquidacion path with 1861 fallback.
            assert ws_client.call_liquidacion_x_coe.call_count == 1
            assert ws_client.call_ajuste_x_coe.call_count == 1
            assert result.total_procesados_ok == 1
