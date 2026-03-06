from __future__ import annotations

from app.extensions import db
from app.models import WslpgParameter


def test_create_parameter(app):
    with app.app_context():
        param = WslpgParameter()
        param.tabla = "tipoGrano"
        param.codigo = "15"
        param.descripcion = "TRIGO PAN"
        param.datos_extra = {"vigente": True}
        db.session.add(param)
        db.session.commit()

        found = WslpgParameter.query.filter_by(tabla="tipoGrano", codigo="15").first()
        assert found is not None
        assert found.descripcion == "TRIGO PAN"
        assert found.datos_extra["vigente"] is True


def test_unique_constraint(app):
    import pytest
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        p1 = WslpgParameter(tabla="tipoGrano", codigo="15", descripcion="TRIGO PAN")
        db.session.add(p1)
        db.session.commit()

        p2 = WslpgParameter(tabla="tipoGrano", codigo="15", descripcion="DUPLICADO")
        db.session.add(p2)
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_lookup_helper(app):
    with app.app_context():
        p = WslpgParameter(tabla="puerto", codigo="14", descripcion="OTROS")
        db.session.add(p)
        db.session.commit()

        desc = WslpgParameter.lookup("puerto", "14")
        assert desc == "OTROS"

        missing = WslpgParameter.lookup("puerto", "999")
        assert missing is None
