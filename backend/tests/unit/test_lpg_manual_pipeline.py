"""Unit tests for LpgManualWsService.

Tests follow strict TDD: written before the implementation.
Cover fetch_only + fetch_and_persist + typed exception contracts.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

# These imports will fail (RED) until lpg_manual_pipeline.py is created.
from app.services.lpg_manual_pipeline import (
    ArcaWsError,
    CoeAlreadyExistsError,
    InvalidCoeFormatError,
    LpgManualWsService,
    TaxpayerConfigInvalidError,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class _FakeTaxpayer:
    """Lightweight stand-in for Taxpayer model (avoids SQLAlchemy instrumentation)."""

    def __init__(
        self,
        *,
        id: int = 1,
        cuit: str = "20304050607",
        cuit_representado: str | None = "30711165378",
        cert_crt_path: str | None = "/tmp/test.crt",
        cert_key_path: str | None = "/tmp/test.key",
        ambiente: str = "homologacion",
    ) -> None:
        self.id = id
        self.cuit = cuit
        self.empresa = "Test SA"
        self.cuit_representado = cuit_representado
        self.cert_crt_path = cert_crt_path
        self.cert_key_path = cert_key_path
        self.ambiente = ambiente


_TAXPAYER = _FakeTaxpayer()

MINIMAL_WS_RESULT: dict = {
    "data": {
        "ptoEmision": "1",
        "nroOrden": "100",
        "estado": "AC",
        "fechaLiquidacion": "2024-03-15",
    }
}

MINIMAL_AJUSTE_WS_RESULT: dict = {
    "data": {
        "ajusteUnificado": {
            "ptoEmision": "2",
            "nroOrden": "200",
            "estado": "AC",
        }
    }
}


# ---------------------------------------------------------------------------
# fetch_only — invalid input / config
# ---------------------------------------------------------------------------


class TestFetchOnlyInvalidInput:
    def test_invalid_coe_format_empty_string(self, app):
        """fetch_only raises InvalidCoeFormatError for an empty COE string."""
        with app.app_context():
            svc = LpgManualWsService()
            with pytest.raises(InvalidCoeFormatError):
                svc.fetch_only(_TAXPAYER, "")

    def test_invalid_coe_format_too_short(self, app):
        """fetch_only raises InvalidCoeFormatError for a COE that is too short."""
        with app.app_context():
            svc = LpgManualWsService()
            with pytest.raises(InvalidCoeFormatError):
                svc.fetch_only(_TAXPAYER, "12345")  # < 6 digits

    def test_invalid_coe_format_non_numeric(self, app):
        """fetch_only raises InvalidCoeFormatError for a non-numeric COE."""
        with app.app_context():
            svc = LpgManualWsService()
            with pytest.raises(InvalidCoeFormatError):
                svc.fetch_only(_TAXPAYER, "3301ABCD0001")

    def test_taxpayer_invalid_config_raises_typed_error(self, app):
        """fetch_only raises TaxpayerConfigInvalidError when validate_taxpayer_ws_config fails."""
        with app.app_context():
            svc = LpgManualWsService()
            with patch(
                "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config",
                side_effect=ValueError("sin certificados"),
            ):
                with pytest.raises(TaxpayerConfigInvalidError, match="sin certificados"):
                    svc.fetch_only(_TAXPAYER, "330130301001")


# ---------------------------------------------------------------------------
# fetch_only — happy paths
# ---------------------------------------------------------------------------


class TestFetchOnlyHappyPath:
    def test_happy_path_liquidacion(self, app):
        """fetch_only returns ws_result, tipo_documento=LPG, and preview dict."""
        with app.app_context():
            svc = LpgManualWsService()
            with patch(
                "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
            ), patch(
                "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
            ) as mock_build:
                mock_ws = MagicMock()
                mock_ws.call_liquidacion_x_coe.return_value = MINIMAL_WS_RESULT
                mock_build.return_value = mock_ws

                result = svc.fetch_only(_TAXPAYER, "330130301001")

            assert result["tipo_documento"] == "LPG"
            assert result["ws_result"] == MINIMAL_WS_RESULT
            assert isinstance(result["preview"], dict)
            mock_ws.call_liquidacion_x_coe.assert_called_once_with(
                330130301001, pdf="N"
            )

    def test_happy_path_ajuste_via_1861(self, app):
        """fetch_only falls back to call_ajuste_x_coe when call_liquidacion_x_coe raises error 1861."""
        with app.app_context():
            svc = LpgManualWsService()
            with patch(
                "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
            ), patch(
                "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
            ) as mock_build:
                mock_ws = MagicMock()
                mock_ws.call_liquidacion_x_coe.side_effect = Exception("1861")
                mock_ws.call_ajuste_x_coe.return_value = MINIMAL_AJUSTE_WS_RESULT
                mock_build.return_value = mock_ws

                result = svc.fetch_only(_TAXPAYER, "330130301001")

            assert result["tipo_documento"] == "AJUSTE"
            assert result["ws_result"] == MINIMAL_AJUSTE_WS_RESULT
            mock_ws.call_ajuste_x_coe.assert_called_once_with(330130301001, pdf="N")

    def test_parser_fallback(self, app):
        """fetch_only falls back to call_ajuste_x_coe when primary call raises a generic parser exception."""
        with app.app_context():
            svc = LpgManualWsService()
            with patch(
                "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
            ), patch(
                "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
            ) as mock_build:
                mock_ws = MagicMock()
                mock_ws.call_liquidacion_x_coe.side_effect = Exception("parser error: unexpected token")
                mock_ws.call_ajuste_x_coe.return_value = MINIMAL_AJUSTE_WS_RESULT
                mock_build.return_value = mock_ws

                result = svc.fetch_only(_TAXPAYER, "330130301001")

            assert result["tipo_documento"] == "AJUSTE"

    def test_ws_error_raises_arca_ws_error(self, app):
        """fetch_only raises ArcaWsError when both WS calls fail."""
        with app.app_context():
            svc = LpgManualWsService()
            with patch(
                "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
            ), patch(
                "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
            ) as mock_build:
                mock_ws = MagicMock()
                mock_ws.call_liquidacion_x_coe.side_effect = Exception("timeout")
                mock_ws.call_ajuste_x_coe.side_effect = Exception("ajuste timeout")
                mock_build.return_value = mock_ws

                with pytest.raises(ArcaWsError):
                    svc.fetch_only(_TAXPAYER, "330130301001")


# ---------------------------------------------------------------------------
# fetch_only — no DB writes invariant
# ---------------------------------------------------------------------------


class TestFetchOnlyNoDbWrites:
    def test_no_db_writes(self, app):
        """fetch_only must NOT write to the database (no LpgDocument, no CoeEstado, no AuditEvent)."""
        from app.extensions import db
        from app.models import AuditEvent, CoeEstado, LpgDocument

        with app.app_context():
            doc_count_before = db.session.query(LpgDocument).count()
            estado_count_before = db.session.query(CoeEstado).count()
            audit_count_before = db.session.query(AuditEvent).count()

            svc = LpgManualWsService()
            with patch(
                "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
            ), patch(
                "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
            ) as mock_build:
                mock_ws = MagicMock()
                mock_ws.call_liquidacion_x_coe.return_value = MINIMAL_WS_RESULT
                mock_build.return_value = mock_ws

                svc.fetch_only(_TAXPAYER, "330130301001")

            assert db.session.query(LpgDocument).count() == doc_count_before
            assert db.session.query(CoeEstado).count() == estado_count_before
            assert db.session.query(AuditEvent).count() == audit_count_before


# ---------------------------------------------------------------------------
# fetch_and_persist — happy path, duplicate, audit event
# ---------------------------------------------------------------------------


class TestFetchAndPersist:
    def test_happy_path(self, app):
        """fetch_and_persist calls fetch_only, persists LpgDocument, returns it."""
        from app.models import LpgDocument

        with app.app_context():
            svc = LpgManualWsService()

            fake_doc = MagicMock(spec=LpgDocument)
            fake_doc.id = 42
            fake_doc.coe = "330130301001"

            with patch.object(
                svc, "fetch_only", return_value={"ws_result": MINIMAL_WS_RESULT, "tipo_documento": "LPG", "preview": {}}
            ), patch(
                "app.services.lpg_manual_pipeline.coe_already_exists", return_value=None
            ), patch(
                "app.services.lpg_manual_pipeline.save_lpg_document_from_ws",
                return_value=fake_doc,
            ), patch(
                "app.services.lpg_manual_pipeline.db"
            ) as mock_db:
                result = svc.fetch_and_persist(_TAXPAYER, "330130301001")

            assert result is fake_doc

    def test_duplicate_raises_with_existing_id(self, app):
        """fetch_and_persist raises CoeAlreadyExistsError with the existing doc's id."""
        from app.models import LpgDocument

        with app.app_context():
            svc = LpgManualWsService()
            existing = MagicMock(spec=LpgDocument)
            existing.id = 77

            with patch.object(
                svc, "fetch_only", return_value={"ws_result": MINIMAL_WS_RESULT, "tipo_documento": "LPG", "preview": {}}
            ), patch(
                "app.services.lpg_manual_pipeline.coe_already_exists",
                return_value=existing,
            ):
                with pytest.raises(CoeAlreadyExistsError) as exc_info:
                    svc.fetch_and_persist(_TAXPAYER, "330130301001")

                assert exc_info.value.coe_id == 77

    def test_audit_event_payload_shape(self, app):
        """fetch_and_persist writes an AuditEvent with the expected payload shape."""
        from app.extensions import db as real_db
        from app.models import AuditEvent, LpgDocument

        with app.app_context():
            svc = LpgManualWsService()

            fake_doc = MagicMock(spec=LpgDocument)
            fake_doc.id = 42
            fake_doc.coe = "330130301001"

            with patch.object(
                svc,
                "fetch_only",
                return_value={"ws_result": MINIMAL_WS_RESULT, "tipo_documento": "LPG", "preview": {}},
            ), patch(
                "app.services.lpg_manual_pipeline.coe_already_exists", return_value=None
            ), patch(
                "app.services.lpg_manual_pipeline.save_lpg_document_from_ws",
                return_value=fake_doc,
            ):
                audit_count_before = real_db.session.query(AuditEvent).count()
                svc.fetch_and_persist(_TAXPAYER, "330130301001")
                audit_events = real_db.session.query(AuditEvent).all()

                # One new audit event was added
                assert len(audit_events) == audit_count_before + 1
                ev = audit_events[-1]
                assert ev.operation == "coe_carga_manual"
                assert ev.taxpayer_id == _TAXPAYER.id
                assert ev.metadata_json["coe"] == "330130301001"
                assert ev.metadata_json["tipo_documento"] == "LPG"
                assert ev.metadata_json["lpg_document_id"] == 42
