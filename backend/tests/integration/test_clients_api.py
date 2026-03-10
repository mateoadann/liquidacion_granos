from __future__ import annotations

import io

from app.models import Taxpayer
from app.services.crypto_service import decrypt_secret


def _base_payload(**overrides):
    payload = {
        "empresa": "Acopio SA",
        "cuit": "20304050607",
        "cuit_representado": "27333444559",
        "ambiente": "homologacion",
        "clave_fiscal": "clave-inicial",
    }
    payload.update(overrides)
    return payload


def _create_client(client, headers, **overrides):
    response = client.post("/api/clients", json=_base_payload(**overrides), headers=headers)
    assert response.status_code == 201
    return response.get_json()


def test_create_client_ok(client, auth_headers):
    response = client.post("/api/clients", json=_base_payload(), headers=auth_headers)

    assert response.status_code == 201
    body = response.get_json()
    assert body["empresa"] == "Acopio SA"
    assert body["cuit"] == "20304050607"
    assert body["has_clave_fiscal"] is True
    assert "clave_fiscal_encrypted" not in body


def test_create_client_duplicate_cuit_returns_409(client, auth_headers):
    _create_client(client, auth_headers)

    response = client.post(
        "/api/clients",
        json=_base_payload(
            empresa="Otra Empresa",
            cuit_representado="20999888777",
            clave_fiscal="otra-clave",
        ),
        headers=auth_headers,
    )

    assert response.status_code == 409


def test_patch_without_clave_fiscal_keeps_has_clave_fiscal(client, auth_headers):
    created = _create_client(client, auth_headers)

    response = client.patch(
        f"/api/clients/{created['id']}",
        json={"empresa": "Acopio SA Actualizada"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["empresa"] == "Acopio SA Actualizada"
    assert body["has_clave_fiscal"] is True


def test_patch_with_clave_fiscal_reencrypts(app, client, auth_headers):
    created = _create_client(client, auth_headers)
    client_id = created["id"]

    with app.app_context():
        before = Taxpayer.query.get(client_id)
        previous_cipher = before.clave_fiscal_encrypted

    response = client.patch(
        f"/api/clients/{client_id}",
        json={"clave_fiscal": "nueva-clave-fiscal"},
        headers=auth_headers,
    )

    assert response.status_code == 200

    with app.app_context():
        after = Taxpayer.query.get(client_id)
        assert after.clave_fiscal_encrypted != previous_cipher
        assert decrypt_secret(after.clave_fiscal_encrypted) == "nueva-clave-fiscal"


def test_logical_delete_sets_activo_false(app, client, auth_headers):
    created = _create_client(client, auth_headers)
    client_id = created["id"]

    response = client.delete(f"/api/clients/{client_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["activo"] is False

    with app.app_context():
        stored = Taxpayer.query.get(client_id)
        assert stored is not None
        assert stored.activo is False


def test_upload_certificates_valid_pair(client, cert_pair_bytes, auth_headers):
    created = _create_client(client, auth_headers)
    cert_bytes, key_bytes = cert_pair_bytes

    response = client.post(
        f"/api/clients/{created['id']}/certificates",
        data={
            "cert_file": (io.BytesIO(cert_bytes), "mi_cert.crt"),
            "key_file": (io.BytesIO(key_bytes), "mi_private.key"),
        },
        content_type="multipart/form-data",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["client"]["cert_crt_filename"] == "mi_cert.crt"
    assert body["client"]["cert_key_filename"] == "mi_private.key"
    assert body["certificates"]["has_certificates"] is True


def test_upload_certificates_invalid_pair_returns_422(
    client, cert_pair_bytes, mismatched_private_key_bytes, auth_headers
):
    created = _create_client(client, auth_headers)
    cert_bytes, _ = cert_pair_bytes

    response = client.post(
        f"/api/clients/{created['id']}/certificates",
        data={
            "cert_file": (io.BytesIO(cert_bytes), "mi_cert.crt"),
            "key_file": (io.BytesIO(mismatched_private_key_bytes), "mi_private.key"),
        },
        content_type="multipart/form-data",
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_validate_config_incomplete(client, auth_headers):
    created = _create_client(client, auth_headers)

    response = client.post(f"/api/clients/{created['id']}/validate-config", headers=auth_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["has_empresa"] is True
    assert body["has_cuit"] is True
    assert body["has_cuit_representado"] is True
    assert body["has_clave_fiscal"] is True
    assert body["has_certificates"] is False
    assert body["ready_for_playwright"] is False


def test_validate_config_complete(client, cert_pair_bytes, auth_headers):
    created = _create_client(client, auth_headers)
    cert_bytes, key_bytes = cert_pair_bytes

    upload = client.post(
        f"/api/clients/{created['id']}/certificates",
        data={
            "cert_file": (io.BytesIO(cert_bytes), "mi_cert.crt"),
            "key_file": (io.BytesIO(key_bytes), "mi_private.key"),
        },
        content_type="multipart/form-data",
        headers=auth_headers,
    )
    assert upload.status_code == 200

    response = client.post(f"/api/clients/{created['id']}/validate-config", headers=auth_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["has_certificates"] is True
    assert body["certificates_valid"] is True
    assert body["ready_for_playwright"] is True
