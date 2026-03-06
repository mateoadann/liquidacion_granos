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
    responses = {
        "tipoGranoConsultar": {
            "tipoGrano": [
                {"codTipoGrano": 15, "descTipoGrano": "TRIGO PAN"},
                {"codTipoGrano": 2, "descTipoGrano": "MAIZ"},
            ]
        },
        "puertoConsultar": {
            "puerto": [
                {"codPuerto": 14, "desPuerto": "OTROS"},
            ]
        },
        "provinciasConsultar": {
            "provincia": [
                {"codProvincia": 3, "desProvincia": "CORDOBA"},
            ]
        },
        "tipoDeduccionConsultar": {
            "tipoDeduccion": [
                {"codigoConcepto": "OD", "descripcionConcepto": "Otras Deducciones"},
                {"codigoConcepto": "GA", "descripcionConcepto": "Comision o Gastos Administrativos"},
            ]
        },
        "tipoRetencionConsultar": {
            "tipoRetencion": [
                {"codigoConcepto": "RG", "descripcionConcepto": "Retencion Ganancias"},
                {"codigoConcepto": "RI", "descripcionConcepto": "Retencion IVA"},
            ]
        },
        "codigoGradoReferenciaConsultar": {
            "gradoRef": [
                {"codGradoRef": "G2", "descGradoRef": "Grado 2"},
            ]
        },
        "codigoGradoEntregadoXTipoGranoConsultar": {
            "gradoEnt": [
                {"codGradoEnt": "G2", "descGradoEnt": "Grado 2"},
            ]
        },
        "localidadXProvinciaConsultar": {
            "localidad": [
                {"codLocalidad": 1443, "descLocalidad": "BENGOLEA"},
            ]
        },
        "tipoOperacionXActividadConsultar": {
            "tipoOperacion": [
                {"codTipoOperacion": 1, "descTipoOperacion": "Compraventa"},
                {"codTipoOperacion": 2, "descTipoOperacion": "Consignacion"},
            ]
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
