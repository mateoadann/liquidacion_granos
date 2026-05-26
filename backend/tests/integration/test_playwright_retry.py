from __future__ import annotations

from types import SimpleNamespace

from app.extensions import db
from app.models import ExtractionJob, Taxpayer


def _create_taxpayer(*, cuit: str = "20111111111", empresa: str = "Test SA") -> Taxpayer:
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


def _create_failed_job(
    *,
    taxpayer_id: int,
    operation: str = "playwright_lpg_run",
    failure_phase: str | None = "LISTING_COES",
    payload: dict | None = None,
) -> ExtractionJob:
    job = ExtractionJob()
    job.taxpayer_id = taxpayer_id
    job.operation = operation
    job.status = "failed"
    job.failure_phase = failure_phase
    job.payload = payload or {
        "fecha_desde": "01/01/2026",
        "fecha_hasta": "26/02/2026",
        "taxpayer_ids": [taxpayer_id],
        "timeout_ms": 30000,
        "type_delay_ms": 80,
    }
    db.session.add(job)
    db.session.commit()
    return job


def _install_dummy_queue(monkeypatch) -> list[dict]:
    """Reemplaza get_queue y la función del worker. Devuelve una lista que se
    va llenando con cada enqueue, para que el test pueda inspeccionar."""
    captured: list[dict] = []

    def dummy_job(*args, **kwargs):
        return None

    class DummyQueue:
        name = "playwright"

        def __init__(self):
            self._counter = 0

        def enqueue(self, func, **kwargs):
            self._counter += 1
            captured.append({"func": func, "kwargs": kwargs})
            return SimpleNamespace(id=f"rq-job-{self._counter}")

    queue_instance = DummyQueue()
    monkeypatch.setattr("app.api.playwright.get_queue", lambda _name: queue_instance)
    monkeypatch.setattr(
        "app.workers.playwright_jobs.run_playwright_pipeline_job",
        dummy_job,
    )
    return captured


class TestManualRetryEndpoint:
    def test_retry_failed_job_creates_new_job(self, client, monkeypatch, auth_headers):
        taxpayer = _create_taxpayer()
        original = _create_failed_job(taxpayer_id=taxpayer.id)
        enqueues = _install_dummy_queue(monkeypatch)

        response = client.post(
            f"/api/playwright/lpg/jobs/{original.id}/retry", headers=auth_headers
        )

        assert response.status_code == 202
        body = response.get_json()
        assert body["job"]["status"] == "pending"
        assert body["job"]["payload"]["retry_of_job_id"] == original.id
        assert body["job"]["payload"]["taxpayer_ids"] == [taxpayer.id]
        # Re-uses the same date params from the original payload.
        assert body["job"]["payload"]["fecha_desde"] == "01/01/2026"
        assert body["job"]["payload"]["fecha_hasta"] == "26/02/2026"

        assert len(enqueues) == 1
        assert enqueues[0]["kwargs"]["taxpayer_ids"] == [taxpayer.id]

    def test_retry_rejects_non_failed_job(self, client, monkeypatch, auth_headers):
        taxpayer = _create_taxpayer()
        original = _create_failed_job(taxpayer_id=taxpayer.id)
        original.status = "completed"
        db.session.commit()
        _install_dummy_queue(monkeypatch)

        response = client.post(
            f"/api/playwright/lpg/jobs/{original.id}/retry", headers=auth_headers
        )

        assert response.status_code == 409
        assert "failed" in response.get_json()["error"]

    def test_retry_404_on_unknown_job(self, client, monkeypatch, auth_headers):
        _install_dummy_queue(monkeypatch)
        response = client.post(
            "/api/playwright/lpg/jobs/999999/retry", headers=auth_headers
        )
        assert response.status_code == 404

    def test_retry_works_on_scheduler_job(self, client, monkeypatch, auth_headers):
        """Manual retry no discrimina por operation: scheduler jobs también."""
        taxpayer = _create_taxpayer()
        original = _create_failed_job(
            taxpayer_id=taxpayer.id, operation="scheduler_lpg_extract"
        )
        _install_dummy_queue(monkeypatch)

        response = client.post(
            f"/api/playwright/lpg/jobs/{original.id}/retry", headers=auth_headers
        )

        assert response.status_code == 202
        body = response.get_json()
        # The new job is a *manual* operation (not scheduler), so it doesn't
        # touch scheduler_ultimo_* columns. Different from auto-retry behaviour.
        assert body["job"]["operation"] == "playwright_lpg_run"


class TestAutoRetrySchedulerHelper:
    """Tests del helper _auto_retry_scheduler_job_if_eligible del worker.

    Importamos el helper directamente porque la ruta completa del worker
    requiere ejecutar el pipeline Playwright real. Mockeamos get_queue.
    """

    def test_scheduler_failed_transient_gets_retried(self, app, monkeypatch):
        from app.workers import playwright_jobs as worker

        captured: list[dict] = []

        class DummyQueue:
            name = "playwright"

            def enqueue(self, func, **kwargs):
                captured.append({"func": func, "kwargs": kwargs})
                return SimpleNamespace(id="rq-retry-1")

        monkeypatch.setattr(worker, "get_queue", lambda _n: DummyQueue())

        with app.app_context():
            taxpayer = _create_taxpayer()
            failed = _create_failed_job(
                taxpayer_id=taxpayer.id,
                operation="scheduler_lpg_extract",
                failure_phase="LISTING_COES",
            )

            new_job = worker._auto_retry_scheduler_job_if_eligible(failed)

            assert new_job is not None
            assert new_job.operation == "scheduler_lpg_extract_retry"
            assert new_job.status == "pending"
            assert new_job.payload["retry_count"] == 1
            assert new_job.payload["previous_job_id"] == failed.id
            assert new_job.payload["taxpayer_ids"] == [taxpayer.id]
            assert len(captured) == 1

    def test_manual_failed_does_not_get_auto_retried(self, app, monkeypatch):
        from app.workers import playwright_jobs as worker

        captured: list[dict] = []
        monkeypatch.setattr(
            worker, "get_queue",
            lambda _n: SimpleNamespace(name="playwright", enqueue=lambda f, **k: captured.append(k) or SimpleNamespace(id="x")),
        )

        with app.app_context():
            taxpayer = _create_taxpayer()
            failed = _create_failed_job(
                taxpayer_id=taxpayer.id, operation="playwright_lpg_run"
            )

            new_job = worker._auto_retry_scheduler_job_if_eligible(failed)

            assert new_job is None
            assert captured == []

    def test_scheduler_retry_does_not_chain_indefinitely(self, app, monkeypatch):
        """Un job que ya es retry (retry_count=1) no debe auto-retriarse otra vez."""
        from app.workers import playwright_jobs as worker

        captured: list[dict] = []
        monkeypatch.setattr(
            worker, "get_queue",
            lambda _n: SimpleNamespace(name="playwright", enqueue=lambda f, **k: captured.append(k) or SimpleNamespace(id="x")),
        )

        with app.app_context():
            taxpayer = _create_taxpayer()
            already_retried = _create_failed_job(
                taxpayer_id=taxpayer.id,
                operation="scheduler_lpg_extract_retry",
                payload={
                    "fecha_desde": "01/01/2026",
                    "fecha_hasta": "26/02/2026",
                    "taxpayer_ids": [taxpayer.id],
                    "timeout_ms": 30000,
                    "type_delay_ms": 80,
                    "retry_count": 1,
                    "previous_job_id": 999,
                },
            )

            new_job = worker._auto_retry_scheduler_job_if_eligible(already_retried)

            assert new_job is None
            assert captured == []
