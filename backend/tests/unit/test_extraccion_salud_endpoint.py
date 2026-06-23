from __future__ import annotations


def test_salud_requires_auth(client):
    res = client.get("/api/extracciones/salud")
    assert res.status_code == 401


def test_salud_returns_shape(client, auth_headers):
    res = client.get("/api/extracciones/salud", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "resumen" in data
    assert "clientes" in data
    assert "generado_en" in data
    assert set(data["resumen"].keys()) == {"verde", "amarillo", "rojo", "gris"}
