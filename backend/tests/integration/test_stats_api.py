from __future__ import annotations

from app.extensions import db
from app.models import Taxpayer, ExtractionJob, LpgDocument


def _create_taxpayer(*, cuit: str, empresa: str, activo: bool = True, playwright_enabled: bool = True) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.playwright_enabled = playwright_enabled
    item.activo = activo
    db.session.add(item)
    db.session.commit()
    return item


def _create_job(*, taxpayer_id: int, status: str, operation: str = "playwright_lpg_run") -> ExtractionJob:
    job = ExtractionJob()
    job.taxpayer_id = taxpayer_id
    job.operation = operation
    job.status = status
    job.payload = {}
    db.session.add(job)
    db.session.commit()
    return job


def _create_coe(*, taxpayer_id: int, coe: str) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = coe
    doc.pto_emision = 1
    doc.nro_orden = 1
    doc.estado = "AC"
    doc.raw_data = {}
    db.session.add(doc)
    db.session.commit()
    return doc


class TestStatsEndpoint:
    def test_stats_returns_counts(self, client, auth_headers):
        t1 = _create_taxpayer(cuit="20111111111", empresa="Empresa 1", activo=True)
        t2 = _create_taxpayer(cuit="20222222222", empresa="Empresa 2", activo=True)
        _create_taxpayer(cuit="20333333333", empresa="Empresa 3", activo=False)

        _create_job(taxpayer_id=t1.id, status="completed")
        _create_job(taxpayer_id=t1.id, status="completed")
        _create_job(taxpayer_id=t2.id, status="failed")

        _create_coe(taxpayer_id=t1.id, coe="123456789")
        _create_coe(taxpayer_id=t1.id, coe="123456790")
        _create_coe(taxpayer_id=t2.id, coe="123456791")

        response = client.get("/api/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["clients_active"] == 2
        assert data["clients_inactive"] == 1
        assert data["clients_total"] == 3
        assert data["jobs_total"] == 3
        assert data["jobs_completed"] == 2
        assert data["jobs_failed"] == 1
        assert data["coes_total"] == 3

    def test_stats_empty_db(self, client, auth_headers):
        response = client.get("/api/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["clients_active"] == 0
        assert data["clients_total"] == 0
        assert data["jobs_total"] == 0
        assert data["coes_total"] == 0
