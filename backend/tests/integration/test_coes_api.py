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
