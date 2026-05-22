from __future__ import annotations

from app.extensions import db
from app.models import CoeEstado, Taxpayer, LpgDocument


def _create_taxpayer(*, cuit: str, empresa: str) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.activo = True
    db.session.add(item)
    db.session.commit()
    return item


def _create_coe(*, taxpayer_id: int, coe: str, estado: str = "AC") -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.estado = estado
    doc.tipo_documento = "LPG"
    db.session.add(doc)
    db.session.commit()
    return doc


def _create_coe_estado(
    *, doc: LpgDocument, cuit_empresa: str, estado: str
) -> CoeEstado:
    entry = CoeEstado()
    entry.coe = doc.coe
    entry.lpg_document_id = doc.id
    entry.cuit_empresa = cuit_empresa
    entry.estado = estado
    db.session.add(entry)
    db.session.commit()
    return entry


def test_list_coes_empty(client, auth_headers):
    response = client.get("/api/coes", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["coes"] == []
    assert data["total"] == 0


def test_list_coes_returns_data(client, auth_headers):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789012", estado="AC")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789013", estado="AN")

    response = client.get("/api/coes", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 2
    assert len(data["coes"]) == 2


def test_list_coes_filter_by_taxpayer(client, auth_headers):
    t1 = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    t2 = _create_taxpayer(cuit="20222222222", empresa="Otro SA")
    _create_coe(taxpayer_id=t1.id, coe="123456789012")
    _create_coe(taxpayer_id=t2.id, coe="123456789013")

    response = client.get(f"/api/coes?taxpayer_id={t1.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["coe"] == "123456789012"


def test_list_coes_filter_by_estado(client, auth_headers):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789012", estado="AC")
    _create_coe(taxpayer_id=taxpayer.id, coe="123456789013", estado="AN")

    response = client.get("/api/coes?estado=AC", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["estado"] == "AC"


def test_list_coes_filter_by_estado_ciclo(client, auth_headers):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    doc_pend = _create_coe(taxpayer_id=taxpayer.id, coe="330230000001")
    doc_carg = _create_coe(taxpayer_id=taxpayer.id, coe="330230000002")
    doc_sin_tracking = _create_coe(taxpayer_id=taxpayer.id, coe="330230000003")
    _create_coe_estado(doc=doc_pend, cuit_empresa=taxpayer.cuit, estado="pendiente")
    _create_coe_estado(doc=doc_carg, cuit_empresa=taxpayer.cuit, estado="cargado")

    response = client.get("/api/coes?estado_ciclo=pendiente", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["coe"] == doc_pend.coe
    assert data["coes"][0]["coe_estado"]["estado"] == "pendiente"

    response = client.get("/api/coes?estado_ciclo=cargado", headers=auth_headers)
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["coe"] == doc_carg.coe

    # Sin filtro: devuelve los 3 (incluido el que no tiene tracking)
    response = client.get("/api/coes", headers=auth_headers)
    assert response.get_json()["total"] == 3
    _ = doc_sin_tracking  # explicit reference


def test_list_coes_filter_by_estado_arca_backward_compat(client, auth_headers):
    """El filtro estado (ARCA) sigue funcionando independientemente de estado_ciclo."""
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    doc_ac = _create_coe(taxpayer_id=taxpayer.id, coe="330230000001", estado="AC")
    _create_coe(taxpayer_id=taxpayer.id, coe="330230000002", estado="AN")
    _create_coe_estado(doc=doc_ac, cuit_empresa=taxpayer.cuit, estado="pendiente")

    response = client.get("/api/coes?estado=AC", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["estado"] == "AC"


def test_list_coes_pagination(client, auth_headers):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    for i in range(15):
        _create_coe(taxpayer_id=taxpayer.id, coe=f"12345678901{i:02d}")

    response = client.get("/api/coes?page=1&per_page=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 15
    assert len(data["coes"]) == 10
    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["pages"] == 2


def test_get_coe_detail(client, auth_headers):
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    coe = _create_coe(taxpayer_id=taxpayer.id, coe="123456789012", estado="AC")

    response = client.get(f"/api/coes/{coe.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == coe.id
    assert data["coe"] == "123456789012"
    assert data["taxpayer"]["empresa"] == "Test SA"


def test_get_coe_not_found(client, auth_headers):
    response = client.get("/api/coes/99999", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# T4: Toggle endpoint contracts (REQ-2, REQ-5)
# ---------------------------------------------------------------------------

def test_toggle_controlada_requires_auth(client):
    """No JWT → 401, no DB mutation."""
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Test SA")
    doc = _create_coe(taxpayer_id=taxpayer.id, coe="123456789012")

    response = client.patch(f"/api/coes/{doc.id}/controlada", json={"controlada": True})
    assert response.status_code == 401

    # DB must not have been mutated
    from app.extensions import db
    from app.models import LpgDocument
    refreshed = db.session.get(LpgDocument, doc.id)
    assert refreshed.controlada is False


def test_toggle_controlada_sets_true_and_audit_emitted(client, auth_headers):
    """Fresh COE → toggle true → DB populated + 1 AuditEvent with correct metadata."""
    from app.extensions import db
    from app.models import AuditEvent

    taxpayer = _create_taxpayer(cuit="20333333333", empresa="Test SA")
    doc = _create_coe(taxpayer_id=taxpayer.id, coe="330000000001")

    audit_count_before = db.session.query(AuditEvent).count()

    response = client.patch(
        f"/api/coes/{doc.id}/controlada",
        json={"controlada": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["controlada"] is True
    assert data["controlada_por"] == "testuser"
    assert data["controlada_por_nombre"] == "Test User"
    assert data["controlada_en"] is not None

    # DB state
    from app.models import LpgDocument
    refreshed = db.session.get(LpgDocument, doc.id)
    assert refreshed.controlada is True
    assert refreshed.controlada_por == "testuser"
    assert refreshed.controlada_por_nombre == "Test User"
    assert refreshed.controlada_en is not None

    # Exactly one new AuditEvent
    audit_count_after = db.session.query(AuditEvent).count()
    assert audit_count_after == audit_count_before + 1

    audit = (
        db.session.query(AuditEvent)
        .filter(AuditEvent.operation == "coe_controlada_toggle")
        .order_by(AuditEvent.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.taxpayer_id == taxpayer.id
    assert audit.level == "info"
    meta = audit.metadata_json
    assert meta["coe_id"] == doc.id
    assert meta["from"] is False
    assert meta["to"] is True
    assert meta["by_username"] == "testuser"
    assert meta["by_nombre"] == "Test User"


def test_toggle_controlada_sets_false_and_clears_actor(client, auth_headers):
    """Pre-seeded controlada=true → toggle false → fields cleared + 1 AuditEvent."""
    from app.extensions import db
    from app.models import AuditEvent, LpgDocument
    from app.time_utils import now_cordoba_naive

    taxpayer = _create_taxpayer(cuit="20444444444", empresa="Test SA 2")
    doc = _create_coe(taxpayer_id=taxpayer.id, coe="330000000002")
    doc.controlada = True
    doc.controlada_por = "someuser"
    doc.controlada_por_nombre = "Some User"
    doc.controlada_en = now_cordoba_naive()
    db.session.commit()

    audit_count_before = db.session.query(AuditEvent).count()

    response = client.patch(
        f"/api/coes/{doc.id}/controlada",
        json={"controlada": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["controlada"] is False
    assert data["controlada_por"] is None
    assert data["controlada_por_nombre"] is None
    assert data["controlada_en"] is None

    # DB cleared
    refreshed = db.session.get(LpgDocument, doc.id)
    assert refreshed.controlada is False
    assert refreshed.controlada_por is None
    assert refreshed.controlada_por_nombre is None
    assert refreshed.controlada_en is None

    # One new AuditEvent
    assert db.session.query(AuditEvent).count() == audit_count_before + 1
    audit = (
        db.session.query(AuditEvent)
        .filter(AuditEvent.operation == "coe_controlada_toggle")
        .order_by(AuditEvent.id.desc())
        .first()
    )
    assert audit.metadata_json["from"] is True
    assert audit.metadata_json["to"] is False


def test_toggle_controlada_noop_no_audit(client, auth_headers):
    """Sending same value as current → 200 with current state, NO new AuditEvent."""
    from app.extensions import db
    from app.models import AuditEvent

    taxpayer = _create_taxpayer(cuit="20555555555", empresa="Test SA 3")
    doc = _create_coe(taxpayer_id=taxpayer.id, coe="330000000003")
    # Doc is already controlada=False by default

    audit_count_before = db.session.query(AuditEvent).count()

    response = client.patch(
        f"/api/coes/{doc.id}/controlada",
        json={"controlada": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["controlada"] is False

    # No new AuditEvent
    assert db.session.query(AuditEvent).count() == audit_count_before


def test_toggle_controlada_invalid_body(client, auth_headers):
    """Missing controlada or wrong type → 400."""
    taxpayer = _create_taxpayer(cuit="20666666666", empresa="Test SA 4")
    doc = _create_coe(taxpayer_id=taxpayer.id, coe="330000000004")

    # Missing key
    response = client.patch(
        f"/api/coes/{doc.id}/controlada",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "error" in response.get_json()

    # Wrong type (string instead of bool)
    response = client.patch(
        f"/api/coes/{doc.id}/controlada",
        json={"controlada": "yes"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_toggle_controlada_not_found(client, auth_headers):
    """Unknown coe_id → 404."""
    response = client.patch(
        "/api/coes/99999/controlada",
        json={"controlada": True},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.get_json()["error"] == "COE no encontrado"


# ---------------------------------------------------------------------------
# T5: List filter + serialization (REQ-3, REQ-4)
# ---------------------------------------------------------------------------

def test_list_coes_filter_by_controlada_true(client, auth_headers):
    """GET /api/coes?controlada=true returns only controlada=true rows."""
    from app.extensions import db

    taxpayer = _create_taxpayer(cuit="20777777771", empresa="Filter SA 1")
    doc1 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000011")
    doc2 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000012")
    doc3 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000013")
    doc1.controlada = True
    doc2.controlada = True
    db.session.commit()
    _ = doc3  # explicit ref

    response = client.get("/api/coes?controlada=true", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 2
    for coe in data["coes"]:
        assert coe["controlada"] is True


def test_list_coes_filter_by_controlada_false(client, auth_headers):
    """GET /api/coes?controlada=false returns only controlada=false rows."""
    from app.extensions import db

    taxpayer = _create_taxpayer(cuit="20777777772", empresa="Filter SA 2")
    doc1 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000021")
    doc2 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000022")
    doc3 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000023")
    doc1.controlada = True
    doc2.controlada = True
    db.session.commit()
    _ = doc3  # explicit ref

    response = client.get("/api/coes?controlada=false", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["coes"][0]["controlada"] is False


def test_list_coes_filter_controlada_invalid_value_ignored(client, auth_headers):
    """?controlada=maybe returns all rows (no filter applied)."""
    from app.extensions import db

    taxpayer = _create_taxpayer(cuit="20777777773", empresa="Filter SA 3")
    doc1 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000031")
    doc2 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000032")
    doc3 = _create_coe(taxpayer_id=taxpayer.id, coe="330000000033")
    doc1.controlada = True
    db.session.commit()
    _ = (doc2, doc3)  # explicit ref

    response = client.get("/api/coes?controlada=maybe", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 3


def test_serialize_coe_includes_controlada_fields_list(client, auth_headers):
    """List response items each contain the 4 controlada keys with correct types."""
    taxpayer = _create_taxpayer(cuit="20888888881", empresa="Serial SA 1")
    _create_coe(taxpayer_id=taxpayer.id, coe="330000000041")

    response = client.get("/api/coes", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    item = data["coes"][0]
    assert "controlada" in item
    assert isinstance(item["controlada"], bool)
    assert "controlada_por" in item
    assert "controlada_por_nombre" in item
    assert "controlada_en" in item
    # Defaults
    assert item["controlada"] is False
    assert item["controlada_por"] is None
    assert item["controlada_por_nombre"] is None
    assert item["controlada_en"] is None


def test_serialize_coe_includes_controlada_fields_detail(client, auth_headers):
    """GET /api/coes/<id> returns the 4 controlada keys."""
    taxpayer = _create_taxpayer(cuit="20888888882", empresa="Serial SA 2")
    doc = _create_coe(taxpayer_id=taxpayer.id, coe="330000000042")

    response = client.get(f"/api/coes/{doc.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert "controlada" in data
    assert isinstance(data["controlada"], bool)
    assert "controlada_por" in data
    assert "controlada_por_nombre" in data
    assert "controlada_en" in data
