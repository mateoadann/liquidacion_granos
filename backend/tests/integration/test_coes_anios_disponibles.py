"""Integration tests for GET /api/coes/anios-disponibles.

Verifies:
- Returns distinct years derived from fechaLiquidacion in datos_limpios,
  ordered descending.
- Years absent from any document are not returned.
- Years that exist only for inactive taxpayers are excluded.
- Endpoint requires authentication (401 without credentials).
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
    datos_limpios: dict | None = None,
) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.estado = "AC"
    doc.tipo_documento = "LPG"
    doc.datos_limpios = datos_limpios
    db.session.add(doc)
    db.session.commit()
    return doc


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_anios_disponibles_requires_auth(client):
    """Endpoint must return 401 when no auth token is provided."""
    resp = client.get("/api/coes/anios-disponibles")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


def test_anios_disponibles_returns_distinct_years_descending(client, auth_headers):
    """Returns the distinct years present in datos_limpios.fechaLiquidacion, desc."""
    t = _mk_taxpayer(cuit="20111111111", empresa="Empresa A")

    _mk_coe(
        taxpayer_id=t.id,
        coe="330100000001",
        datos_limpios={"fechaLiquidacion": "2024-03-15"},
    )
    _mk_coe(
        taxpayer_id=t.id,
        coe="330100000002",
        datos_limpios={"fechaLiquidacion": "2023-11-01"},
    )
    # Second doc for 2024 — must still return 2024 only once (distinct)
    _mk_coe(
        taxpayer_id=t.id,
        coe="330100000003",
        datos_limpios={"fechaLiquidacion": "2024-07-20"},
    )
    _mk_coe(
        taxpayer_id=t.id,
        coe="330100000004",
        datos_limpios={"fechaLiquidacion": "2025-01-05"},
    )

    resp = client.get("/api/coes/anios-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()

    assert "anios" in data
    anios = data["anios"]

    assert anios == sorted(set(anios), reverse=True), "Years must be ordered descending"
    assert 2025 in anios
    assert 2024 in anios
    assert 2023 in anios
    assert anios.count(2024) == 1, "2024 must appear only once (distinct)"


def test_anios_disponibles_empty_when_no_docs(client, auth_headers):
    """Returns an empty list when there are no COE documents at all."""
    resp = client.get("/api/coes/anios-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["anios"] == []


def test_anios_disponibles_skips_docs_without_fecha(client, auth_headers):
    """Docs with null fechaLiquidacion in datos_limpios are ignored."""
    t = _mk_taxpayer(cuit="20222222222", empresa="Empresa B")

    # Doc with no fechaLiquidacion
    _mk_coe(
        taxpayer_id=t.id,
        coe="330100000010",
        datos_limpios={"otrocampo": "x"},
    )
    # Doc with fechaLiquidacion null/missing
    _mk_coe(
        taxpayer_id=t.id,
        coe="330100000011",
        datos_limpios=None,
    )
    # One valid doc
    _mk_coe(
        taxpayer_id=t.id,
        coe="330100000012",
        datos_limpios={"fechaLiquidacion": "2026-05-10"},
    )

    resp = client.get("/api/coes/anios-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["anios"] == [2026]


def test_anios_disponibles_excludes_inactive_taxpayer_years(client, auth_headers):
    """A year that exists ONLY for an inactive taxpayer must not be returned."""
    active = _mk_taxpayer(cuit="20333333333", empresa="Activo SA", activo=True)
    inactive = _mk_taxpayer(cuit="20444444444", empresa="Inactivo SA", activo=False)

    # Active taxpayer has a doc in 2024
    _mk_coe(
        taxpayer_id=active.id,
        coe="330100000020",
        datos_limpios={"fechaLiquidacion": "2024-06-01"},
    )
    # Inactive taxpayer has docs in 2024 AND 2022
    _mk_coe(
        taxpayer_id=inactive.id,
        coe="330100000021",
        datos_limpios={"fechaLiquidacion": "2024-09-15"},
    )
    _mk_coe(
        taxpayer_id=inactive.id,
        coe="330100000022",
        datos_limpios={"fechaLiquidacion": "2022-03-20"},
    )

    resp = client.get("/api/coes/anios-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    anios = data["anios"]

    # 2024 should appear (active taxpayer has it)
    assert 2024 in anios
    # 2022 must NOT appear (only inactive taxpayer has it)
    assert 2022 not in anios, "Year only present for inactive taxpayer must be excluded"


def test_anios_disponibles_uses_credito_fecha_fallback(client, auth_headers):
    """For AJUSTE docs, fechaLiquidacion may live at credito_fechaLiquidacion."""
    t = _mk_taxpayer(cuit="20555555555", empresa="Empresa C")

    _mk_coe(
        taxpayer_id=t.id,
        coe="330200000030",
        datos_limpios={"credito_fechaLiquidacion": "2021-08-15"},
    )

    resp = client.get("/api/coes/anios-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()

    assert 2021 in data["anios"]
