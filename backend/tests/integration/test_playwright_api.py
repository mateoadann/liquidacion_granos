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


def test_run_playwright_requires_dates(client, auth_headers):
    response = client.post("/api/playwright/lpg/run", json={}, headers=auth_headers)

    assert response.status_code == 400
    assert "fecha_desde" in response.get_json()["error"]


def test_run_playwright_validates_taxpayer_ids(client, auth_headers):
    response = client.post(
        "/api/playwright/lpg/run",
        json={
            "fecha_desde": "01/01/2026",
            "fecha_hasta": "26/02/2026",
            "taxpayer_ids": ["1", 2],
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "taxpayer_ids" in response.get_json()["error"]


def test_run_playwright_creates_one_job_per_taxpayer(client, monkeypatch, auth_headers):
    """N taxpayers seleccionados ⇒ N ExtractionJobs creados y N enqueues."""
    taxpayer_one = _create_taxpayer(cuit="20111111111", empresa="Empresa Uno")
    taxpayer_two = _create_taxpayer(cuit="20222222222", empresa="Empresa Dos")
    taxpayer_three = _create_taxpayer(cuit="20333333333", empresa="Empresa Tres")
    captured_calls: list[dict[str, object]] = []

    def dummy_job(*args, **kwargs):
        return None

    class DummyQueue:
        name = "playwright"

        def __init__(self):
            self._counter = 0

        def enqueue(self, func, **kwargs):
            self._counter += 1
            captured_calls.append({"func": func, "kwargs": kwargs})
            return SimpleNamespace(id=f"rq-job-{self._counter}")

    queue_instance = DummyQueue()
    monkeypatch.setattr("app.api.playwright.get_queue", lambda _name: queue_instance)
    monkeypatch.setattr(
        "app.workers.playwright_jobs.run_playwright_pipeline_job",
        dummy_job,
    )

    response = client.post(
        "/api/playwright/lpg/run",
        json={
            "fecha_desde": "01/01/2026",
            "fecha_hasta": "26/02/2026",
            "taxpayer_ids": [taxpayer_one.id, taxpayer_two.id, taxpayer_three.id],
            "timeout_ms": 45000,
            "type_delay_ms": 120,
        },
        headers=auth_headers,
    )

    assert response.status_code == 202
    body = response.get_json()
    assert "jobs" in body and isinstance(body["jobs"], list)
    assert len(body["jobs"]) == 3

    # Each job is bound to exactly one taxpayer and has its own rq_job_id
    job_taxpayer_ids = [j["payload"]["taxpayer_ids"] for j in body["jobs"]]
    assert job_taxpayer_ids == [
        [taxpayer_one.id],
        [taxpayer_two.id],
        [taxpayer_three.id],
    ]
    rq_job_ids = [j["payload"]["rq_job_id"] for j in body["jobs"]]
    assert rq_job_ids == ["rq-job-1", "rq-job-2", "rq-job-3"]

    # The first job carries the progress-feedback keys (null on pending)
    for key in (
        "current_phase",
        "current_message",
        "failure_phase",
        "failure_message_user",
        "failure_message_technical",
    ):
        assert key in body["jobs"][0]
        assert body["jobs"][0][key] is None

    # Worker was called once per taxpayer with the taxpayer's own id only
    assert len(captured_calls) == 3
    assert [c["kwargs"]["taxpayer_ids"] for c in captured_calls] == [
        [taxpayer_one.id],
        [taxpayer_two.id],
        [taxpayer_three.id],
    ]


def test_run_playwright_single_taxpayer_creates_single_job(client, monkeypatch, auth_headers):
    """Caso límite: 1 solo taxpayer seleccionado debe seguir funcionando."""
    taxpayer = _create_taxpayer(cuit="20111111111", empresa="Solo Uno")

    def dummy_job(*args, **kwargs):
        return None

    class DummyQueue:
        name = "playwright"

        def enqueue(self, func, **kwargs):
            return SimpleNamespace(id="rq-job-solo")

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
            "taxpayer_ids": [taxpayer.id],
        },
        headers=auth_headers,
    )

    assert response.status_code == 202
    body = response.get_json()
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["payload"]["taxpayer_ids"] == [taxpayer.id]
