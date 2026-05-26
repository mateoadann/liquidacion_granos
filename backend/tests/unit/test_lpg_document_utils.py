"""Unit tests for the shared WS helpers extracted to lpg_document_utils.

These tests cover the 4 helpers that are extracted from LpgPlaywrightPipelineService:
  - build_ws_client_for_taxpayer
  - save_lpg_document_from_ws
  - validate_taxpayer_ws_config
  - coe_already_exists
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.lpg_document import LpgDocument
from app.models.taxpayer import Taxpayer
from app.services.lpg_document_utils import (
    build_ws_client_for_taxpayer,
    coe_already_exists,
    save_lpg_document_from_ws,
    validate_taxpayer_ws_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeTaxpayer:
    """Lightweight stand-in for Taxpayer that avoids SQLAlchemy instrumentation."""

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


def _make_taxpayer(**kwargs) -> _FakeTaxpayer:
    return _FakeTaxpayer(**kwargs)


MINIMAL_WS_RESULT: dict = {
    "data": {
        "ptoEmision": "1",
        "nroOrden": "100",
        "estado": "AC",
    }
}


# ---------------------------------------------------------------------------
# build_ws_client_for_taxpayer
# ---------------------------------------------------------------------------


class TestBuildWsClientForTaxpayer:
    def test_uses_taxpayer_certs(self, app):
        """build_ws_client_for_taxpayer sets cert paths from taxpayer attrs."""
        tp = _make_taxpayer(
            cert_crt_path="/path/to/taxpayer.crt",
            cert_key_path="/path/to/taxpayer.key",
        )
        with app.app_context():
            with patch(
                "app.services.lpg_document_utils.ArcaWslpgClient"
            ) as MockClient, patch(
                "app.services.lpg_document_utils.ArcaDiscoveryConfig"
            ) as MockConfig:
                fake_cfg = MagicMock()
                MockConfig.from_env.return_value = fake_cfg
                build_ws_client_for_taxpayer(tp)

                assert fake_cfg.cert_path == "/path/to/taxpayer.crt"
                assert fake_cfg.key_path == "/path/to/taxpayer.key"
                MockClient.assert_called_once_with(config=fake_cfg)

    def test_uses_taxpayer_cuit_representado(self, app):
        """build_ws_client_for_taxpayer sets cuit_representada from taxpayer."""
        tp = _make_taxpayer(cuit_representado="30999888777")
        with app.app_context():
            with patch(
                "app.services.lpg_document_utils.ArcaWslpgClient"
            ) as MockClient, patch(
                "app.services.lpg_document_utils.ArcaDiscoveryConfig"
            ) as MockConfig:
                fake_cfg = MagicMock()
                MockConfig.from_env.return_value = fake_cfg
                build_ws_client_for_taxpayer(tp)

                assert fake_cfg.cuit_representada == "30999888777"

    def test_ta_path_scoped_to_taxpayer_id(self, app):
        """build_ws_client_for_taxpayer scopes ta_path to taxpayer id."""
        tp = _make_taxpayer(id=42)
        with app.app_context():
            with patch("app.services.lpg_document_utils.ArcaWslpgClient"), patch(
                "app.services.lpg_document_utils.ArcaDiscoveryConfig"
            ) as MockConfig, patch.dict(
                "os.environ", {"ARCA_TA_PATH": "/tmp/ta"}, clear=False
            ):
                fake_cfg = MagicMock()
                fake_cfg.ta_path = None
                MockConfig.from_env.return_value = fake_cfg
                build_ws_client_for_taxpayer(tp)

                assert fake_cfg.ta_path.endswith("taxpayer_42")


# ---------------------------------------------------------------------------
# save_lpg_document_from_ws
# ---------------------------------------------------------------------------


class TestSaveLpgDocumentFromWs:
    def test_creates_lpg_document_and_pendiente_state(self, app):
        """save_lpg_document_from_ws persists LpgDocument and triggers crear_pendiente."""
        from app.extensions import db

        with app.app_context():
            with patch(
                "app.services.lpg_document_utils.DatosLimpiosBuilder"
            ) as MockBuilder, patch(
                "app.services.lpg_document_utils.crear_pendiente"
            ) as mock_crear:
                mock_builder_inst = MagicMock()
                MockBuilder.return_value = mock_builder_inst

                doc = save_lpg_document_from_ws(
                    taxpayer_id=1,
                    coe="330130301001",
                    ws_result=MINIMAL_WS_RESULT,
                    tipo_documento="LPG",
                )

                assert doc is not None
                assert doc.taxpayer_id == 1
                assert doc.coe == "330130301001"
                assert doc.tipo_documento == "LPG"
                assert doc.id is not None  # committed

                mock_builder_inst.process_document.assert_called_once_with(doc)
                mock_crear.assert_called_once_with(doc)

    def test_runs_datos_limpios_builder(self, app):
        """save_lpg_document_from_ws always runs DatosLimpiosBuilder."""
        with app.app_context():
            with patch(
                "app.services.lpg_document_utils.DatosLimpiosBuilder"
            ) as MockBuilder, patch(
                "app.services.lpg_document_utils.crear_pendiente"
            ):
                mock_builder_inst = MagicMock()
                MockBuilder.return_value = mock_builder_inst

                save_lpg_document_from_ws(
                    taxpayer_id=2,
                    coe="330130302002",
                    ws_result={"data": {}},
                    tipo_documento="AJUSTE",
                )

                assert MockBuilder.call_count == 1
                assert mock_builder_inst.process_document.call_count == 1

    def test_stores_raw_data(self, app):
        """save_lpg_document_from_ws persists the raw WS payload."""
        from app.extensions import db

        ws = {"data": {"ptoEmision": "5", "nroOrden": "999", "estado": "AC"}}
        with app.app_context():
            with patch("app.services.lpg_document_utils.DatosLimpiosBuilder"), patch(
                "app.services.lpg_document_utils.crear_pendiente"
            ):
                doc = save_lpg_document_from_ws(
                    taxpayer_id=3,
                    coe="330130303003",
                    ws_result=ws,
                )
                assert doc.raw_data == ws


# ---------------------------------------------------------------------------
# validate_taxpayer_ws_config
# ---------------------------------------------------------------------------


class TestValidateTaxpayerWsConfig:
    def test_raises_when_certs_missing(self):
        """validate_taxpayer_ws_config raises ValueError when cert paths absent."""
        tp = _make_taxpayer(cert_crt_path=None, cert_key_path=None)
        with pytest.raises(ValueError, match="sin certificados"):
            validate_taxpayer_ws_config(tp)

    def test_raises_when_cuit_representado_missing(self):
        """validate_taxpayer_ws_config raises ValueError when cuit_representado absent."""
        tp = _make_taxpayer(cuit_representado=None)
        with pytest.raises(ValueError, match="sin cuit_representado"):
            validate_taxpayer_ws_config(tp)

    def test_raises_when_cert_invalid(self):
        """validate_taxpayer_ws_config raises ValueError when cert validation fails."""
        from app.services.certificate_validator import CertificateValidationError

        tp = _make_taxpayer(
            cert_crt_path="/fake/bad.crt", cert_key_path="/fake/bad.key"
        )
        with patch(
            "app.services.lpg_document_utils.validate_certificate_and_key_paths",
            side_effect=CertificateValidationError("bad cert"),
        ):
            with pytest.raises(ValueError, match="Certificados inválidos"):
                validate_taxpayer_ws_config(tp)

    def test_passes_for_valid_config(self):
        """validate_taxpayer_ws_config returns None when config is valid."""
        tp = _make_taxpayer()
        with patch(
            "app.services.lpg_document_utils.validate_certificate_and_key_paths",
            return_value=None,
        ):
            result = validate_taxpayer_ws_config(tp)
            assert result is None


# ---------------------------------------------------------------------------
# coe_already_exists
# ---------------------------------------------------------------------------


class TestCoeAlreadyExists:
    def test_returns_doc_when_exists(self, app):
        """coe_already_exists returns the LpgDocument when the COE is stored."""
        from app.extensions import db

        with app.app_context():
            doc = LpgDocument()
            doc.taxpayer_id = 10
            doc.coe = "330130301001"
            doc.tipo_documento = "LPG"
            doc.raw_data = {}
            db.session.add(doc)
            db.session.commit()

            result = coe_already_exists(10, "330130301001")
            assert result is not None
            assert result.coe == "330130301001"

    def test_returns_none_when_not_exists(self, app):
        """coe_already_exists returns None when the COE is not stored."""
        with app.app_context():
            result = coe_already_exists(10, "000000000000")
            assert result is None

    def test_scoped_to_taxpayer_id(self, app):
        """coe_already_exists does not return docs from another taxpayer."""
        from app.extensions import db

        with app.app_context():
            doc = LpgDocument()
            doc.taxpayer_id = 5
            doc.coe = "330130305005"
            doc.tipo_documento = "LPG"
            doc.raw_data = {}
            db.session.add(doc)
            db.session.commit()

            # Same COE, different taxpayer → None
            result = coe_already_exists(99, "330130305005")
            assert result is None
