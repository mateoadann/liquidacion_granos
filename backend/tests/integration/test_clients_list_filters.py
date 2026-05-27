"""Tests para los filtros de GET /api/clients agregados por la issue #97.

Cubren:
- search por cuit_representado (nuevo campo, antes sólo empresa + cuit).
- has_certificates=true/false.
- order_by=empresa (alfabético) y default por id.
- Combinaciones (active + has_certificates + order).
"""
from __future__ import annotations

from app.extensions import db
from app.models import Taxpayer


def _create_taxpayer(
    *,
    empresa: str,
    cuit: str,
    cuit_representado: str,
    activo: bool = True,
    cert_paths: tuple[str | None, str | None] = (None, None),
) -> Taxpayer:
    item = Taxpayer()
    item.empresa = empresa
    item.cuit = cuit
    item.cuit_representado = cuit_representado
    item.clave_fiscal_encrypted = "test"
    item.playwright_enabled = True
    item.activo = activo
    crt, key = cert_paths
    item.cert_crt_path = crt
    item.cert_key_path = key
    db.session.add(item)
    db.session.commit()
    return item


def test_list_search_matches_cuit_representado(app, client, auth_headers):
    with app.app_context():
        _create_taxpayer(
            empresa="MANASSERO HNOS SRL",
            cuit="20279638612",
            cuit_representado="30710910193",
        )
        _create_taxpayer(
            empresa="Garcia Hnos SRL",
            cuit="20210132237",
            cuit_representado="30555555555",
        )

    response = client.get(
        "/api/clients?search=30710", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.get_json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["empresa"] == "MANASSERO HNOS SRL"


def test_list_has_certificates_true_filters_only_loaded(app, client, auth_headers):
    with app.app_context():
        _create_taxpayer(
            empresa="Con Cert",
            cuit="20111111111",
            cuit_representado="30111111111",
            cert_paths=("/path/cert.crt", "/path/cert.key"),
        )
        _create_taxpayer(
            empresa="Sin Cert",
            cuit="20222222222",
            cuit_representado="30222222222",
        )

    response = client.get(
        "/api/clients?has_certificates=true", headers=auth_headers
    )
    assert response.status_code == 200
    items = response.get_json()
    assert len(items) == 1
    assert items[0]["empresa"] == "Con Cert"


def test_list_has_certificates_false_includes_partial_cert(app, client, auth_headers):
    """Sólo cert pero no key (o viceversa) cuenta como 'sin certificado'."""
    with app.app_context():
        _create_taxpayer(
            empresa="Completo",
            cuit="20111111111",
            cuit_representado="30111111111",
            cert_paths=("/path/cert.crt", "/path/cert.key"),
        )
        _create_taxpayer(
            empresa="Solo CRT",
            cuit="20222222222",
            cuit_representado="30222222222",
            cert_paths=("/path/cert.crt", None),
        )
        _create_taxpayer(
            empresa="Nada",
            cuit="20333333333",
            cuit_representado="30333333333",
        )

    response = client.get(
        "/api/clients?has_certificates=false", headers=auth_headers
    )
    assert response.status_code == 200
    empresas = sorted(item["empresa"] for item in response.get_json())
    assert empresas == ["Nada", "Solo CRT"]


def test_list_order_by_empresa_returns_alphabetical(app, client, auth_headers):
    with app.app_context():
        _create_taxpayer(
            empresa="Zeta SA",
            cuit="20111111111",
            cuit_representado="30111111111",
        )
        _create_taxpayer(
            empresa="Alfa SA",
            cuit="20222222222",
            cuit_representado="30222222222",
        )
        _create_taxpayer(
            empresa="Beta SA",
            cuit="20333333333",
            cuit_representado="30333333333",
        )

    response = client.get(
        "/api/clients?order_by=empresa", headers=auth_headers
    )
    assert response.status_code == 200
    empresas = [item["empresa"] for item in response.get_json()]
    assert empresas == ["Alfa SA", "Beta SA", "Zeta SA"]


def test_list_default_order_is_by_id(app, client, auth_headers):
    with app.app_context():
        _create_taxpayer(
            empresa="Zeta SA",
            cuit="20111111111",
            cuit_representado="30111111111",
        )
        _create_taxpayer(
            empresa="Alfa SA",
            cuit="20222222222",
            cuit_representado="30222222222",
        )

    response = client.get("/api/clients", headers=auth_headers)
    assert response.status_code == 200
    empresas = [item["empresa"] for item in response.get_json()]
    # Default order es por id ascendente, así que el primero insertado va primero.
    assert empresas == ["Zeta SA", "Alfa SA"]


def test_list_combines_filters(app, client, auth_headers):
    """active=true + has_certificates=true + order_by=empresa juntos."""
    with app.app_context():
        _create_taxpayer(
            empresa="Zeta Activo Con Cert",
            cuit="20111111111",
            cuit_representado="30111111111",
            cert_paths=("/path/cert.crt", "/path/cert.key"),
        )
        _create_taxpayer(
            empresa="Alfa Activo Sin Cert",
            cuit="20222222222",
            cuit_representado="30222222222",
        )
        _create_taxpayer(
            empresa="Beta Inactivo Con Cert",
            cuit="20333333333",
            cuit_representado="30333333333",
            activo=False,
            cert_paths=("/path/cert.crt", "/path/cert.key"),
        )

    response = client.get(
        "/api/clients?active=true&has_certificates=true&order_by=empresa",
        headers=auth_headers,
    )
    assert response.status_code == 200
    empresas = [item["empresa"] for item in response.get_json()]
    assert empresas == ["Zeta Activo Con Cert"]


def test_list_invalid_has_certificates_returns_400(app, client, auth_headers):
    response = client.get(
        "/api/clients?has_certificates=maybe", headers=auth_headers
    )
    assert response.status_code == 400


def test_list_invalid_order_by_returns_400(app, client, auth_headers):
    response = client.get(
        "/api/clients?order_by=created_at", headers=auth_headers
    )
    assert response.status_code == 400


def test_list_paginated_respects_order_by(app, client, auth_headers):
    with app.app_context():
        for letter in ["C", "A", "B"]:
            _create_taxpayer(
                empresa=f"{letter} Empresa",
                cuit=f"2011111111{letter[0]}".replace("A", "0").replace("B", "1").replace("C", "2"),
                cuit_representado=f"3011111111{letter[0]}".replace("A", "0").replace("B", "1").replace("C", "2"),
            )

    response = client.get(
        "/api/clients?page=1&per_page=20&order_by=empresa", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.get_json()
    empresas = [item["empresa"] for item in body["clients"]]
    assert empresas == ["A Empresa", "B Empresa", "C Empresa"]
