"""Integration tests for POST /api/coes/consultar.

Key invariants:
  - All paths (success and error) MUST NOT write to the DB.
  - 200 with duplicado=false for a new COE.
  - 200 with duplicado=true + coe_id for an already-persisted COE.
  - 400 for invalid COE format.
  - 404 for unknown taxpayer_id.
  - 422 for taxpayer without valid certs.
  - 422 for ARCA WS functional error.
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


def _patch_fetch_only(ws_result=None, tipo="LPG"):
    """Context manager: patch LpgManualWsService.fetch_only to return a canned result."""
    ws = ws_result or FAKE_WS_RESULT
    preview = {
        "tipo_documento": tipo,
        "pto_emision": 1,
        "nro_orden": 100,
        "estado": "AC",
        "raw_data": ws,
    }
    return patch(
        "app.api.coes.LpgManualWsService.fetch_only",
        return_value={"ws_result": ws, "tipo_documento": tipo, "preview": preview},
    )


# ---------------------------------------------------------------------------
# Happy path — no duplicate
# ---------------------------------------------------------------------------


def test_consultar_200_no_duplicate(client, auth_headers):
    """POST /consultar returns 200 with duplicado=false for a new COE."""
    tp = _create_taxpayer()

    with _patch_fetch_only():
        resp = client.post(
            "/api/coes/consultar",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["duplicado"] is False
    assert data["coe_id"] is None
    assert data["tipo_documento"] == "LPG"
    assert isinstance(data["preview"], dict)


def test_consultar_200_with_duplicate(client, auth_headers):
    """POST /consultar returns 200 with duplicado=true and coe_id for an already-loaded COE."""
    tp = _create_taxpayer()
    existing = _create_doc(taxpayer_id=tp.id, coe="330130301001")

    with _patch_fetch_only():
        resp = client.post(
            "/api/coes/consultar",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["duplicado"] is True
    assert data["coe_id"] == existing.id


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_consultar_400_invalid_coe(client, auth_headers):
    """POST /consultar returns 400 when COE format is invalid."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import InvalidCoeFormatError

    with patch(
        "app.api.coes.LpgManualWsService.fetch_only",
        side_effect=InvalidCoeFormatError("COE inválido"),
    ):
        resp = client.post(
            "/api/coes/consultar",
            json={"coe": "ABC", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_consultar_400_missing_taxpayer_id(client, auth_headers):
    """POST /consultar returns 400 when taxpayer_id is missing."""
    resp = client.post(
        "/api/coes/consultar",
        json={"coe": "330130301001"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_consultar_404_taxpayer_not_found(client, auth_headers):
    """POST /consultar returns 404 when taxpayer_id does not exist."""
    resp = client.post(
        "/api/coes/consultar",
        json={"coe": "330130301001", "taxpayer_id": 99999},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_consultar_422_taxpayer_no_certs(client, auth_headers):
    """POST /consultar returns 422 when taxpayer has no certs."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import TaxpayerConfigInvalidError

    with patch(
        "app.api.coes.LpgManualWsService.fetch_only",
        side_effect=TaxpayerConfigInvalidError("sin certificados"),
    ):
        resp = client.post(
            "/api/coes/consultar",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 422
    assert "error" in resp.get_json()


def test_consultar_422_ws_error(client, auth_headers):
    """POST /consultar returns 422 when ARCA WS reports a functional error."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import ArcaWsError

    with patch(
        "app.api.coes.LpgManualWsService.fetch_only",
        side_effect=ArcaWsError("timeout"),
    ):
        resp = client.post(
            "/api/coes/consultar",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert resp.status_code == 422
    assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# No-DB-writes invariant: ALL paths
# ---------------------------------------------------------------------------


def test_consultar_no_db_writes_success(client, auth_headers):
    """POST /consultar (success path) must NOT write to any table."""
    tp = _create_taxpayer()

    doc_count = db.session.query(LpgDocument).count()
    estado_count = db.session.query(CoeEstado).count()
    audit_count = db.session.query(AuditEvent).count()

    with _patch_fetch_only():
        client.post(
            "/api/coes/consultar",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert db.session.query(LpgDocument).count() == doc_count
    assert db.session.query(CoeEstado).count() == estado_count
    assert db.session.query(AuditEvent).count() == audit_count


def test_consultar_no_db_writes_error_path(client, auth_headers):
    """POST /consultar (error path) must NOT write to any table."""
    tp = _create_taxpayer()

    from app.services.lpg_manual_pipeline import ArcaWsError

    doc_count = db.session.query(LpgDocument).count()
    estado_count = db.session.query(CoeEstado).count()
    audit_count = db.session.query(AuditEvent).count()

    with patch(
        "app.api.coes.LpgManualWsService.fetch_only",
        side_effect=ArcaWsError("boom"),
    ):
        client.post(
            "/api/coes/consultar",
            json={"coe": "330130301001", "taxpayer_id": tp.id},
            headers=auth_headers,
        )

    assert db.session.query(LpgDocument).count() == doc_count
    assert db.session.query(CoeEstado).count() == estado_count
    assert db.session.query(AuditEvent).count() == audit_count
