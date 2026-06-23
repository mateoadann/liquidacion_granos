from app.models import Taxpayer
from app.extensions import db


def _crear_cliente(app):
    with app.app_context():
        t = Taxpayer(empresa="Test SA", cuit="20111111110", cuit_representado="30111111110")
        db.session.add(t)
        db.session.commit()
        return t.id


def test_patch_clave_sets_timestamp(app, client, auth_headers):
    tid = _crear_cliente(app)
    res = client.patch(
        f"/api/clients/{tid}",
        json={"clave_fiscal": "nueva-clave-123"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    with app.app_context():
        t = Taxpayer.query.get(tid)
        assert t.clave_fiscal_actualizada_en is not None


def test_patch_without_clave_does_not_set_timestamp(app, client, auth_headers):
    tid = _crear_cliente(app)
    res = client.patch(
        f"/api/clients/{tid}",
        json={"empresa": "Otro Nombre SA"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    with app.app_context():
        t = Taxpayer.query.get(tid)
        assert t.clave_fiscal_actualizada_en is None
