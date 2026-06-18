"""Tests for Bug 1 (tipo_cte filter) and Bug 2 (inactive taxpayer exclusion)
in GET /api/coes.

Classification source of truth: json_v7_exporter._build_comprobante
  - NL: tipo_documento == "AJUSTE"
  - F2: not ajuste AND codTipoOperacion == "2"
  - F1: not ajuste AND (codTipoOperacion is null OR != "2")
"""
from __future__ import annotations

from app.extensions import db
from app.models import LpgDocument, Taxpayer


def _mk_taxpayer(*, cuit: str, empresa: str, activo: bool = True) -> Taxpayer:
    t = Taxpayer()
    t.cuit = cuit
    t.empresa = empresa
    t.cuit_representado = cuit
    t.clave_fiscal_encrypted = "test"
    t.activo = activo
    db.session.add(t)
    db.session.commit()
    return t


def _mk_coe(
    *,
    taxpayer_id: int,
    coe: str,
    tipo_documento: str = "LPG",
    datos_limpios: dict | None = None,
    estado: str = "AC",
) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.estado = estado
    doc.tipo_documento = tipo_documento
    doc.datos_limpios = datos_limpios
    db.session.add(doc)
    db.session.commit()
    return doc


# ---------------------------------------------------------------------------
# Bug 1 — tipo_cte filter correctness
# ---------------------------------------------------------------------------

def test_tipo_cte_f2_excludes_ajuste_with_3302_prefix(client, auth_headers):
    """F2 filter must NOT return AJUSTE docs even when their COE starts with 3302."""
    t = _mk_taxpayer(cuit="20111111111", empresa="Empresa A")

    # AJUSTE with a 3302-prefixed COE — old (buggy) filter returned this
    _mk_coe(
        taxpayer_id=t.id,
        coe="330200001234",
        tipo_documento="AJUSTE",
        datos_limpios={"codTipoOperacion": 2},
    )
    # True F2: not an ajuste, codTipoOperacion == 2
    f2_doc = _mk_coe(
        taxpayer_id=t.id,
        coe="330200005678",
        tipo_documento="LPG",
        datos_limpios={"codTipoOperacion": 2},
    )

    resp = client.get("/api/coes?tipo_cte=F2", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert f2_doc.id in returned_ids, "True F2 document must be returned"
    assert data["total"] == 1, (
        "Only 1 F2 doc expected; AJUSTE must be excluded even with 3302 prefix"
    )


def test_tipo_cte_f1_returns_null_cod_tipo_operacion(client, auth_headers):
    """F1 filter returns docs with codTipoOperacion null (or absent) and NOT ajuste."""
    t = _mk_taxpayer(cuit="20222222222", empresa="Empresa B")

    f1_null = _mk_coe(
        taxpayer_id=t.id,
        coe="330100001111",
        tipo_documento="LPG",
        datos_limpios=None,  # null datos_limpios
    )
    f1_no_key = _mk_coe(
        taxpayer_id=t.id,
        coe="330100002222",
        tipo_documento="LPG",
        datos_limpios={"otrocampo": "x"},  # key absent
    )
    # These should NOT appear under F1
    _mk_coe(
        taxpayer_id=t.id,
        coe="330200003333",
        tipo_documento="LPG",
        datos_limpios={"codTipoOperacion": 2},  # F2
    )
    _mk_coe(
        taxpayer_id=t.id,
        coe="330200004444",
        tipo_documento="AJUSTE",
        datos_limpios=None,  # NL
    )

    resp = client.get("/api/coes?tipo_cte=F1", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert f1_null.id in returned_ids
    assert f1_no_key.id in returned_ids
    assert data["total"] == 2


def test_tipo_cte_f1_also_matches_non_2_cod_tipo_operacion(client, auth_headers):
    """F1 also covers docs where codTipoOperacion exists but is not '2'."""
    t = _mk_taxpayer(cuit="20333333333", empresa="Empresa C")

    f1_other = _mk_coe(
        taxpayer_id=t.id,
        coe="330100009999",
        tipo_documento="LPG",
        datos_limpios={"codTipoOperacion": 1},  # value 1 → F1
    )

    resp = client.get("/api/coes?tipo_cte=F1", headers=auth_headers)
    assert resp.status_code == 200
    returned_ids = {c["id"] for c in resp.get_json()["coes"]}
    assert f1_other.id in returned_ids


def test_tipo_cte_nl_returns_only_ajuste(client, auth_headers):
    """NL filter returns only tipo_documento=AJUSTE documents."""
    t = _mk_taxpayer(cuit="20444444444", empresa="Empresa D")

    ajuste = _mk_coe(
        taxpayer_id=t.id,
        coe="330200007777",
        tipo_documento="AJUSTE",
        datos_limpios={"codTipoOperacion": 2},
    )
    _mk_coe(
        taxpayer_id=t.id,
        coe="330100008888",
        tipo_documento="LPG",
        datos_limpios=None,
    )

    resp = client.get("/api/coes?tipo_cte=NL", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert ajuste.id in returned_ids
    assert data["total"] == 1


def test_tipo_cte_multiple_types_combined(client, auth_headers):
    """Requesting F1,NL returns union of both without F2."""
    t = _mk_taxpayer(cuit="20555555555", empresa="Empresa E")

    f1 = _mk_coe(
        taxpayer_id=t.id,
        coe="330100000001",
        tipo_documento="LPG",
        datos_limpios=None,
    )
    nl = _mk_coe(
        taxpayer_id=t.id,
        coe="330200000002",
        tipo_documento="AJUSTE",
        datos_limpios=None,
    )
    f2 = _mk_coe(
        taxpayer_id=t.id,
        coe="330200000003",
        tipo_documento="LPG",
        datos_limpios={"codTipoOperacion": 2},
    )

    resp = client.get("/api/coes?tipo_cte=F1,NL", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert f1.id in returned_ids
    assert nl.id in returned_ids
    assert f2.id not in returned_ids
    assert data["total"] == 2


# ---------------------------------------------------------------------------
# Bug 2 — inactive taxpayers excluded from /coes
# ---------------------------------------------------------------------------

def test_inactive_taxpayer_coes_not_returned(client, auth_headers):
    """COEs belonging to a Taxpayer with activo=False must never appear in /coes."""
    active = _mk_taxpayer(cuit="20666666666", empresa="Activo SA", activo=True)
    inactive = _mk_taxpayer(cuit="20777777777", empresa="Inactivo SA", activo=False)

    active_doc = _mk_coe(taxpayer_id=active.id, coe="330100000010")
    inactive_doc = _mk_coe(taxpayer_id=inactive.id, coe="330100000011")

    resp = client.get("/api/coes", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert active_doc.id in returned_ids
    assert inactive_doc.id not in returned_ids
    assert data["total"] == 1


def test_inactive_taxpayer_excluded_with_estado_ciclo_filter(client, auth_headers):
    """Inactive taxpayer exclusion holds even when estado_ciclo filter is applied
    (both JOIN on Taxpayer and outerjoin on CoeEstado must coexist)."""
    from app.models import CoeEstado

    active = _mk_taxpayer(cuit="20888888888", empresa="Activo SA 2", activo=True)
    inactive = _mk_taxpayer(cuit="20999999999", empresa="Inactivo SA 2", activo=False)

    active_doc = _mk_coe(taxpayer_id=active.id, coe="330100000020")
    inactive_doc = _mk_coe(taxpayer_id=inactive.id, coe="330100000021")

    # Add CoeEstado for both
    for doc in (active_doc, inactive_doc):
        ce = CoeEstado()
        ce.coe = doc.coe
        ce.lpg_document_id = doc.id
        ce.cuit_empresa = "20000000000"
        ce.estado = "pendiente"
        db.session.add(ce)
    db.session.commit()

    resp = client.get("/api/coes?estado_ciclo=pendiente", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert active_doc.id in returned_ids
    assert inactive_doc.id not in returned_ids
    assert data["total"] == 1


def test_serialize_coe_includes_cod_tipo_operacion(client, auth_headers):
    """_serialize_coe must expose cod_tipo_operacion from datos_limpios."""
    t = _mk_taxpayer(cuit="20100100100", empresa="Serial SA")
    doc = _mk_coe(
        taxpayer_id=t.id,
        coe="330200099999",
        tipo_documento="LPG",
        datos_limpios={"codTipoOperacion": 2},
    )

    resp = client.get(f"/api/coes/{doc.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "cod_tipo_operacion" in data
    assert data["cod_tipo_operacion"] == 2


# ---------------------------------------------------------------------------
# Regression — codTipoOperacion stored as JSON string "2" (not int 2)
# ---------------------------------------------------------------------------

def test_tipo_cte_f2_matches_string_cod_tipo_operacion(client, auth_headers):
    """When codTipoOperacion is stored as the JSON string "2" (not the int 2),
    the F2 filter must still match it — cast produces '"2"' in that case."""
    t = _mk_taxpayer(cuit="20123456789", empresa="String Cod SA")

    f2_string = _mk_coe(
        taxpayer_id=t.id,
        coe="330200011111",
        tipo_documento="LPG",
        datos_limpios={"codTipoOperacion": "2"},  # stored as JSON string, not int
    )

    resp = client.get("/api/coes?tipo_cte=F2", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert f2_string.id in returned_ids, "F2 filter must match codTipoOperacion stored as JSON string '2'"


def test_tipo_cte_f1_does_not_match_string_cod_tipo_operacion_2(client, auth_headers):
    """When codTipoOperacion is the JSON string "2", the F1 filter must NOT match it."""
    t = _mk_taxpayer(cuit="20987654321", empresa="String Cod F1 SA")

    f2_string = _mk_coe(
        taxpayer_id=t.id,
        coe="330200022222",
        tipo_documento="LPG",
        datos_limpios={"codTipoOperacion": "2"},  # JSON string — should be F2, not F1
    )

    resp = client.get("/api/coes?tipo_cte=F1", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    returned_ids = {c["id"] for c in data["coes"]}

    assert f2_string.id not in returned_ids, "F1 filter must NOT match codTipoOperacion stored as JSON string '2'"


def test_inactive_taxpayer_excluded_when_filtered_by_taxpayer_id(client, auth_headers):
    """Even with an explicit taxpayer_id filter, docs of an inactive taxpayer
    are excluded because the inner JOIN on Taxpayer.activo blocks them."""
    inactive = _mk_taxpayer(cuit="20112233445", empresa="Inactive Filtered SA", activo=False)

    _mk_coe(taxpayer_id=inactive.id, coe="330100033333")

    resp = client.get(f"/api/coes?taxpayer_id={inactive.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["total"] == 0, "Inactive taxpayer's docs must not appear even with explicit taxpayer_id filter"
