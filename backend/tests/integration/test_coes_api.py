from __future__ import annotations

from app.extensions import db
from app.models import Taxpayer, LpgDocument


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
