from __future__ import annotations

from unittest.mock import MagicMock

from app.extensions import db
from app.models import WslpgParameter
from app.services.parameter_sync import ParameterSyncService


def _mock_ws_client():
    client = MagicMock()
    client.send_request.side_effect = _route_mock_request
    client.get_auth_payload.return_value = {"token": "t", "sign": "s", "cuit": 1}
    client.connect.return_value = client
    return client


def _route_mock_request(method_name, data):
    """Mock responses matching real WSLPG SOAP structure (post _safe_serialize)."""
    responses = {
        "tipoGranoConsultar": {
            "granos": {
                "codigoDescripcion": [
                    {"codigo": 15, "descripcion": "TRIGO PAN"},
                    {"codigo": 2, "descripcion": "MAIZ"},
                ]
            }
        },
        "puertoConsultar": {
            "puertos": {
                "codigoDescripcion": [
                    {"codigo": 14, "descripcion": "OTROS"},
                ]
            }
        },
        "provinciasConsultar": {
            "provincias": {
                "codigoDescripcion": [
                    {"codigo": 3, "descripcion": "CORDOBA"},
                ]
            }
        },
        "tipoDeduccionConsultar": {
            "tiposDeduccion": {
                "codigoDescripcion": [
                    {"codigo": "OD", "descripcion": "Otras Deducciones"},
                    {"codigo": "GA", "descripcion": "Comision o Gastos Administrativos"},
                ]
            }
        },
        "tipoRetencionConsultar": {
            "tiposRetencion": {
                "codigoDescripcion": [
                    {"codigo": "RG", "descripcion": "Retencion Ganancias"},
                    {"codigo": "RI", "descripcion": "Retencion IVA"},
                ]
            }
        },
        "codigoGradoReferenciaConsultar": {
            "gradosRef": {
                "codigoDescripcion": [
                    {"codigo": "G2", "descripcion": "Grado 2"},
                ]
            }
        },
        "codigoGradoEntregadoXTipoGranoConsultar": {
            "gradoEnt": {
                "gradoEnt": [
                    {"codigoDescripcion": {"codigo": "G2", "descripcion": "Grado 2"}, "valor": 95.3},
                ]
            }
        },
        "localidadXProvinciaConsultar": {
            "localidades": {
                "codigoDescripcion": [
                    {"codigo": 1443, "descripcion": "BENGOLEA"},
                ]
            }
        },
    }
    return responses.get(method_name, {})


def test_sync_granos(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_tipo_grano()
        assert result["synced"] == 2
        assert WslpgParameter.lookup("tipoGrano", "15") == "TRIGO PAN"
        assert WslpgParameter.lookup("tipoGrano", "2") == "MAIZ"


def test_sync_puertos(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_puertos()
        assert result["synced"] == 1
        assert WslpgParameter.lookup("puerto", "14") == "OTROS"


def test_sync_deducciones(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_tipo_deduccion()
        assert result["synced"] == 2
        assert WslpgParameter.lookup("tipoDeduccion", "OD") == "Otras Deducciones"


def test_sync_retenciones(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_tipo_retencion()
        assert result["synced"] == 2
        assert WslpgParameter.lookup("tipoRetencion", "RG") == "Retencion Ganancias"


def test_sync_all(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        results = service.sync_all()
        assert "tipoGrano" in results
        assert "puerto" in results
        assert "provincia" in results
        assert "tipoDeduccion" in results
        assert "tipoRetencion" in results


def test_sync_upserts_on_duplicate(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        service.sync_tipo_grano()
        assert WslpgParameter.lookup("tipoGrano", "15") == "TRIGO PAN"
        # Segunda sync — debe upsert sin error
        service.sync_tipo_grano()
        assert WslpgParameter.lookup("tipoGrano", "15") == "TRIGO PAN"
