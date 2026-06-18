from __future__ import annotations

from datetime import datetime

import pytest

from app.extensions import db
from app.models import Taxpayer, ExtractionJob, LpgDocument
from app.time_utils import now_cordoba_naive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_taxpayer(*, cuit: str, empresa: str, activo: bool = True) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.playwright_enabled = True
    item.activo = activo
    db.session.add(item)
    db.session.commit()
    return item


def _create_job(
    *,
    taxpayer_id: int,
    status: str,
    finished_at: datetime | None = None,
    operation: str = "playwright_lpg_run",
) -> ExtractionJob:
    job = ExtractionJob()
    job.taxpayer_id = taxpayer_id
    job.operation = operation
    job.status = status
    job.payload = {}
    job.finished_at = finished_at
    db.session.add(job)
    db.session.commit()
    return job


def _create_coe(
    *,
    taxpayer_id: int,
    coe: str,
    fecha_liquidacion: str | None = None,
    tipo_documento: str = "LPG",
    cod_tipo_operacion: int | str | None = None,
) -> LpgDocument:
    """Create an LpgDocument with an optional fechaLiquidacion in datos_limpios."""
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.pto_emision = 1
    doc.nro_orden = 1
    doc.estado = "AC"
    doc.tipo_documento = tipo_documento
    doc.raw_data = {}
    datos: dict = {}
    if fecha_liquidacion:
        datos["fechaLiquidacion"] = fecha_liquidacion
    if cod_tipo_operacion is not None:
        datos["codTipoOperacion"] = cod_tipo_operacion
    doc.datos_limpios = datos
    db.session.add(doc)
    db.session.commit()
    return doc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStatsMensualEndpoint:
    def test_counts_only_coes_in_selected_month(self, client, auth_headers):
        t = _create_taxpayer(cuit="20111111111", empresa="Empresa 1")

        # In-month COEs (June 2025)
        _create_coe(taxpayer_id=t.id, coe="100000001", fecha_liquidacion="2025-06-01")
        _create_coe(taxpayer_id=t.id, coe="100000002", fecha_liquidacion="2025-06-30")

        # Out-of-month COEs (May and July 2025)
        _create_coe(taxpayer_id=t.id, coe="100000003", fecha_liquidacion="2025-05-31")
        _create_coe(taxpayer_id=t.id, coe="100000004", fecha_liquidacion="2025-07-01")

        response = client.get("/api/stats/mensual?mes=6&anio=2025", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["mes"] == 6
        assert data["anio"] == 2025
        assert data["coes_nuevos"] == 2

    def test_coes_desglose_f1_f2_nl(self, client, auth_headers):
        """COEs del mes se desglosan en F1/F2/Aj con la misma clasificación que /coes:
        AJUSTE -> NL, codTipoOperacion==2 -> F2, resto -> F1."""
        t = _create_taxpayer(cuit="20111111111", empresa="Empresa 1")

        # F1: not ajuste, codTipoOperacion null or != 2
        _create_coe(taxpayer_id=t.id, coe="100000001", fecha_liquidacion="2025-06-05")
        _create_coe(taxpayer_id=t.id, coe="100000002", fecha_liquidacion="2025-06-06", cod_tipo_operacion=1)
        # F2: not ajuste, codTipoOperacion == 2 (int and string forms)
        _create_coe(taxpayer_id=t.id, coe="100000003", fecha_liquidacion="2025-06-07", cod_tipo_operacion=2)
        _create_coe(taxpayer_id=t.id, coe="100000004", fecha_liquidacion="2025-06-08", cod_tipo_operacion="2")
        # NL (Aj): AJUSTE regardless of codTipoOperacion
        _create_coe(
            taxpayer_id=t.id, coe="100000005", fecha_liquidacion="2025-06-09",
            tipo_documento="AJUSTE", cod_tipo_operacion=2,
        )

        response = client.get("/api/stats/mensual?mes=6&anio=2025", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["coes_nuevos"] == 5
        assert data["coes_f1"] == 2
        assert data["coes_f2"] == 2
        assert data["coes_nl"] == 1

    def test_counts_only_completed_jobs_in_selected_month(self, client, auth_headers):
        t = _create_taxpayer(cuit="20111111111", empresa="Empresa 1")

        # Completed jobs within June 2025
        _create_job(
            taxpayer_id=t.id,
            status="completed",
            finished_at=datetime(2025, 6, 15, 10, 0, 0),
        )
        _create_job(
            taxpayer_id=t.id,
            status="completed",
            finished_at=datetime(2025, 6, 30, 23, 59, 59),
        )

        # Completed job in a different month
        _create_job(
            taxpayer_id=t.id,
            status="completed",
            finished_at=datetime(2025, 5, 1, 8, 0, 0),
        )

        # Failed job within the month — must NOT count
        _create_job(
            taxpayer_id=t.id,
            status="failed",
            finished_at=datetime(2025, 6, 20, 12, 0, 0),
        )

        response = client.get("/api/stats/mensual?mes=6&anio=2025", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["extracciones_exitosas"] == 2
        # The failed job within the month is counted separately, not as exitosa
        assert data["extracciones_fallidas"] == 1

    def test_docs_from_other_months_excluded(self, client, auth_headers):
        t = _create_taxpayer(cuit="20111111111", empresa="Empresa 1")

        _create_coe(taxpayer_id=t.id, coe="100000001", fecha_liquidacion="2025-01-15")
        _create_coe(taxpayer_id=t.id, coe="100000002", fecha_liquidacion="2025-03-10")

        response = client.get("/api/stats/mensual?mes=2&anio=2025", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["coes_nuevos"] == 0

    def test_inactive_taxpayer_docs_excluded(self, client, auth_headers):
        active_t = _create_taxpayer(cuit="20111111111", empresa="Activa", activo=True)
        inactive_t = _create_taxpayer(cuit="20222222222", empresa="Inactiva", activo=False)

        _create_coe(taxpayer_id=active_t.id, coe="100000001", fecha_liquidacion="2025-06-10")
        _create_coe(taxpayer_id=inactive_t.id, coe="100000002", fecha_liquidacion="2025-06-10")

        response = client.get("/api/stats/mensual?mes=6&anio=2025", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["coes_nuevos"] == 1  # Only the active taxpayer's COE

    def test_invalid_mes_returns_400(self, client, auth_headers):
        response = client.get("/api/stats/mensual?mes=13&anio=2025", headers=auth_headers)
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_invalid_mes_zero_returns_400(self, client, auth_headers):
        response = client.get("/api/stats/mensual?mes=0&anio=2025", headers=auth_headers)
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_non_integer_mes_returns_400(self, client, auth_headers):
        response = client.get("/api/stats/mensual?mes=abc&anio=2025", headers=auth_headers)
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_invalid_anio_returns_400(self, client, auth_headers):
        response = client.get("/api/stats/mensual?mes=6&anio=1800", headers=auth_headers)
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_defaults_to_current_month_when_params_absent(self, client, auth_headers):
        """When no params are given, endpoint returns current month without error."""
        response = client.get("/api/stats/mensual", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()

        now = now_cordoba_naive()
        assert data["mes"] == now.month
        assert data["anio"] == now.year
        assert "coes_nuevos" in data
        assert "extracciones_exitosas" in data

    def test_requires_auth(self, client):
        response = client.get("/api/stats/mensual?mes=6&anio=2025")
        assert response.status_code == 401

    def test_december_boundary_does_not_error(self, client, auth_headers):
        """December month rollover to January of next year must work correctly."""
        t = _create_taxpayer(cuit="20111111111", empresa="Empresa 1")

        _create_coe(taxpayer_id=t.id, coe="100000001", fecha_liquidacion="2025-12-15")
        _create_coe(taxpayer_id=t.id, coe="100000002", fecha_liquidacion="2026-01-01")

        _create_job(
            taxpayer_id=t.id,
            status="completed",
            finished_at=datetime(2025, 12, 31, 23, 59, 59),
        )
        _create_job(
            taxpayer_id=t.id,
            status="completed",
            finished_at=datetime(2026, 1, 1, 0, 0, 0),
        )

        response = client.get("/api/stats/mensual?mes=12&anio=2025", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["coes_nuevos"] == 1
        assert data["extracciones_exitosas"] == 1

    def test_empty_month_returns_zeros(self, client, auth_headers):
        """A month with no data returns zeros, not an error."""
        response = client.get("/api/stats/mensual?mes=1&anio=2000", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["coes_nuevos"] == 0
        assert data["extracciones_exitosas"] == 0
