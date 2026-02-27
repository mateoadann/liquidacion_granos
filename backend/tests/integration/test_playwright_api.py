from __future__ import annotations

from types import SimpleNamespace

from app.extensions import db
from app.models import Taxpayer


def _create_taxpayer(*, cuit: str, empresa: str) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.playwright_enabled = True
    item.activo = True
    db.session.add(item)
    db.session.commit()
    return item


def test_run_playwright_requires_dates(client):
    response = client.post("/api/playwright/lpg/run", json={})

    assert response.status_code == 400
    assert "fecha_desde" in response.get_json()["error"]


def test_run_playwright_validates_taxpayer_ids(client):
    response = client.post(
        "/api/playwright/lpg/run",
        json={
            "fecha_desde": "01/01/2026",
            "fecha_hasta": "26/02/2026",
            "taxpayer_ids": ["1", 2],
        },
    )

    assert response.status_code == 400
    assert "taxpayer_ids" in response.get_json()["error"]


def test_run_playwright_enqueues_job(client, monkeypatch):
    taxpayer_one = _create_taxpayer(cuit="20111111111", empresa="Empresa Uno")
    taxpayer_two = _create_taxpayer(cuit="20222222222", empresa="Empresa Dos")
    captured: dict[str, object] = {}

    def dummy_job(*args, **kwargs):
        return None

    class DummyQueue:
        name = "playwright"

        def enqueue(self, func, **kwargs):
            captured["func"] = func
            captured["kwargs"] = kwargs
            return SimpleNamespace(id="rq-job-123")

    monkeypatch.setattr("app.api.playwright.get_queue", lambda _name: DummyQueue())
    monkeypatch.setattr(
        "app.workers.playwright_jobs.run_playwright_pipeline_job",
        dummy_job,
    )

    response = client.post(
        "/api/playwright/lpg/run",
        json={
            "fecha_desde": "01/01/2026",
            "fecha_hasta": "26/02/2026",
            "taxpayer_ids": [taxpayer_one.id, taxpayer_two.id],
            "timeout_ms": 45000,
            "type_delay_ms": 120,
        },
    )

    assert response.status_code == 202
    body = response.get_json()
    assert body["job"]["status"] == "pending"
    assert body["job"]["payload"]["taxpayer_ids"] == [taxpayer_one.id, taxpayer_two.id]
    assert body["job"]["payload"]["rq_job_id"] == "rq-job-123"
    assert body["job"]["payload"]["queue_name"] == "playwright"

    assert captured["func"] is dummy_job
    assert captured["kwargs"] == {
        "extraction_job_id": body["job"]["id"],
        "fecha_desde": "01/01/2026",
        "fecha_hasta": "26/02/2026",
        "taxpayer_ids": [taxpayer_one.id, taxpayer_two.id],
        "timeout_ms": 45000,
        "type_delay_ms": 120,
        "job_timeout": 3600,
        "result_ttl": 86400,
        "failure_ttl": 86400,
    }
