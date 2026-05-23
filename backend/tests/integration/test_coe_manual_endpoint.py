"""Integration tests for POST /api/coes/manual.

Covers:
  - 201 happy path with CoeEstado=pendiente and AuditEvent row.
  - 400 invalid COE format.
  - 404 taxpayer not found.
  - 409 duplicate (response includes coe_id).
  - 422 taxpayer no certs.
  - 502 WS error.
  - Audit event payload shape verification.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models import AuditEvent, CoeEstado, LpgDocument, Taxpayer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_taxpayer(
    *,
    cuit: str = "20304050607",
    empresa: str = "Test SA",
    cuit_representado: str | None = "30711165378",
    cert_crt_path: str | None = "/tmp/test.crt",
    cert_key_path: str | None = "/tmp/test.key",
    activo: bool = True,
) -> Taxpayer:
    tp = Taxpayer()
    tp.cuit = cuit
    tp.empresa = empresa
    tp.cuit_representado = cuit_representado
    tp.cert_crt_path = cert_crt_path
    tp.cert_key_path = cert_key_path
    tp.clave_fiscal_encrypted = "x"
    tp.activo = activo
    db.session.add(tp)
    db.session.commit()
    return tp


def _create_doc(*, taxpayer_id: int, coe: str) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.tipo_documento = "LPG"
    doc.raw_data = {}
    db.session.add(doc)
    db.session.commit()
    return doc


FAKE_WS_RESULT = {
    "data": {
        "ptoEmision": "1",
        "nroOrden": "100",
        "estado": "AC",
        "fechaLiquidacion": "2024-03-15",
    }
}


def _patch_fetch_and_persist(fake_doc):
    """Context manager: patch LpgManualWsService.fetch_and_persist to return fake_doc."""
    return patch(
        "app.api.coes.LpgManualWsService.fetch_and_persist",
        return_value=fake_doc,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_manual_201_happy_path(client, auth_headers):
    """POST /manual returns 201 with serialized COE on success."""
    tp = _create_taxpayer()

    # Use the real service path — patch WS + cert validation
    with patch(
        "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
    ), patch(
        "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
    ) as mock_build:
        mock_ws = MagicMock()
        mock_ws.call_liquidacion_x_coe.return_value = FAKE_WS_RESULT
        mock_build.return_value = mock_ws

        resp = client.post(
            "/api/coes/manual",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    data = resp.get_json()
    assert data["coe"] == "330130301001"
    assert data["taxpayer_id"] == tp.id
    assert "taxpayer" in data  # include_taxpayer=True


def test_manual_201_creates_coe_estado_pendiente(client, auth_headers):
    """POST /manual creates a CoeEstado with estado=pendiente."""
    tp = _create_taxpayer()

    with patch(
        "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
    ), patch(
        "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
    ) as mock_build:
        mock_ws = MagicMock()
        mock_ws.call_liquidacion_x_coe.return_value = FAKE_WS_RESULT
        mock_build.return_value = mock_ws

        resp = client.post(
            "/api/coes/manual",
            json={"coe": "330130302002", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 201

    doc_id = resp.get_json()["id"]
    coe_estado = db.session.query(CoeEstado).filter_by(lpg_document_id=doc_id).first()
    assert coe_estado is not None
    assert coe_estado.estado == "pendiente"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_manual_400_invalid_coe(client, auth_headers):
    """POST /manual returns 400 when COE format is invalid."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import InvalidCoeFormatError

    with patch(
        "app.api.coes.LpgManualWsService.fetch_and_persist",
        side_effect=InvalidCoeFormatError("COE inválido"),
    ):
        resp = client.post(
            "/api/coes/manual",
            json={"coe": "ABC", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_manual_400_missing_taxpayer_id(client, auth_headers):
    """POST /manual returns 400 when taxpayer_id is missing."""
    resp = client.post(
        "/api/coes/manual",
        json={"coe": "330130301001"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_manual_404_taxpayer_not_found(client, auth_headers):
    """POST /manual returns 404 when taxpayer_id does not exist."""
    resp = client.post(
        "/api/coes/manual",
        json={"coe": "330130301001", "taxpayer_id": 99999},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_manual_409_duplicate(client, auth_headers):
    """POST /manual returns 409 with coe_id when COE already exists."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import CoeAlreadyExistsError

    with patch(
        "app.api.coes.LpgManualWsService.fetch_and_persist",
        side_effect=CoeAlreadyExistsError(coe_id=55),
    ):
        resp = client.post(
            "/api/coes/manual",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 409
    data = resp.get_json()
    assert "error" in data
    assert data["coe_id"] == 55


def test_manual_422_taxpayer_no_certs(client, auth_headers):
    """POST /manual returns 422 when taxpayer has no certs."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import TaxpayerConfigInvalidError

    with patch(
        "app.api.coes.LpgManualWsService.fetch_and_persist",
        side_effect=TaxpayerConfigInvalidError("sin certificados"),
    ):
        resp = client.post(
            "/api/coes/manual",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 422
    assert "error" in resp.get_json()


def test_manual_502_ws_error(client, auth_headers):
    """POST /manual returns 502 when ARCA WS fails."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import ArcaWsError

    with patch(
        "app.api.coes.LpgManualWsService.fetch_and_persist",
        side_effect=ArcaWsError("timeout"),
    ):
        resp = client.post(
            "/api/coes/manual",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 502
    assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# Audit event
# ---------------------------------------------------------------------------


def test_manual_writes_audit_event(client, auth_headers):
    """POST /manual writes an AuditEvent with operation=coe_carga_manual."""
    tp = _create_taxpayer()

    audit_count_before = db.session.query(AuditEvent).count()

    with patch(
        "app.services.lpg_manual_pipeline.validate_taxpayer_ws_config"
    ), patch(
        "app.services.lpg_manual_pipeline.build_ws_client_for_taxpayer"
    ) as mock_build:
        mock_ws = MagicMock()
        mock_ws.call_liquidacion_x_coe.return_value = FAKE_WS_RESULT
        mock_build.return_value = mock_ws

        resp = client.post(
            "/api/coes/manual",
            json={"coe": "330130303003", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 201

    events = db.session.query(AuditEvent).filter_by(operation="coe_carga_manual").all()
    assert len(events) == audit_count_before + 1
    ev = events[-1]
    assert ev.taxpayer_id == tp.id
    assert ev.metadata_json["coe"] == "330130303003"
    assert ev.metadata_json["tipo_documento"] == "LPG"
    assert "lpg_document_id" in ev.metadata_json
