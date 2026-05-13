from __future__ import annotations

from typing import Any

import pytest

from app.extensions import db
from app.models import ExtractionJob, Taxpayer
from app.services.extraction_phases import ExtractionPhase
from app.workers.playwright_jobs import (
    _persist_taxpayer_failure,
    _update_job,
    _update_phase_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _create_taxpayer(*, cuit: str = "20111111111", empresa: str = "Empresa Uno") -> Taxpayer:
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


def _create_job(taxpayer_id: int, payload: dict[str, Any] | None = None) -> ExtractionJob:
    item = ExtractionJob()
    item.taxpayer_id = taxpayer_id
    item.operation = "playwright_lpg_run"
    item.status = "pending"
    item.payload = payload or {
        "progress": {
            "total_clients": 1,
            "completed_clients": 0,
            "running_client_id": None,
            "clients": [
                {
                    "taxpayer_id": taxpayer_id,
                    "empresa": "Empresa Uno",
                    "status": "pending",
                    "error": None,
                    "started_at": None,
                    "finished_at": None,
                    "metrics": {},
                    "current_phase": None,
                    "current_message": None,
                    "failure_phase": None,
                    "failure_message_user": None,
                    "failure_message_technical": None,
                }
            ],
        }
    }
    db.session.add(item)
    db.session.commit()
    return item


# ---------------------------------------------------------------------------
# _update_phase_state — updates job-level and per-client fields, commits
# ---------------------------------------------------------------------------

def test_update_phase_state_updates_job_level_and_per_client_fields(app) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)
    payload = dict(job.payload or {})

    _update_phase_state(
        job.id,
        payload,
        taxpayer_id=taxpayer.id,
        phase=ExtractionPhase.SEARCH_SERVICE,
        message="Buscando el servicio Liquidación primaria de granos...",
    )

    # Job-level columns are persisted via direct setattr in _update_job.
    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed is not None
    assert refreshed.current_phase == ExtractionPhase.SEARCH_SERVICE.value
    assert (
        refreshed.current_message
        == "Buscando el servicio Liquidación primaria de granos..."
    )

    # In-memory payload mutation propagates per-client fields. The same dict is
    # written back to the JSON column by _update_job; that round-trip is
    # outside this unit's contract (and SQLAlchemy nested-dict tracking is a
    # known caveat — see e2e tests below for the DB-level mirror behavior).
    clients = (payload.get("progress") or {}).get("clients") or []
    assert len(clients) == 1
    assert clients[0]["current_phase"] == ExtractionPhase.SEARCH_SERVICE.value
    assert (
        clients[0]["current_message"]
        == "Buscando el servicio Liquidación primaria de granos..."
    )


def test_update_phase_state_multiple_calls_overwrite_previous(app) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)
    payload = dict(job.payload or {})

    _update_phase_state(
        job.id,
        payload,
        taxpayer_id=taxpayer.id,
        phase=ExtractionPhase.LOGIN_START,
        message="Ingresando a ARCA con clave fiscal...",
    )
    _update_phase_state(
        job.id,
        payload,
        taxpayer_id=taxpayer.id,
        phase=ExtractionPhase.LOGIN_CONFIRMED,
        message="Sesión confirmada en ARCA.",
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.current_phase == ExtractionPhase.LOGIN_CONFIRMED.value
    assert refreshed.current_message == "Sesión confirmada en ARCA."


# ---------------------------------------------------------------------------
# RQ retry safety — running clears all 5 phase/failure fields
# ---------------------------------------------------------------------------

def test_update_job_running_clears_stale_phase_and_failure_fields(app) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)

    # Simulate stale fields from a previous failed run.
    job.current_phase = "SEARCH_SERVICE"
    job.current_message = "Buscando el servicio..."
    job.failure_phase = "LOGIN_START"
    job.failure_message_user = "old user msg"
    job.failure_message_technical = "old tech msg"
    job.status = "failed"
    db.session.commit()

    # The worker calls _update_job with the exact kwargs from
    # run_playwright_pipeline_job when transitioning to running.
    from app.time_utils import now_cordoba_naive

    _update_job(
        job.id,
        status="running",
        started_at=now_cordoba_naive(),
        error_message=None,
        current_phase=None,
        current_message=None,
        failure_phase=None,
        failure_message_user=None,
        failure_message_technical=None,
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "running"
    assert refreshed.current_phase is None
    assert refreshed.current_message is None
    assert refreshed.failure_phase is None
    assert refreshed.failure_message_user is None
    assert refreshed.failure_message_technical is None


# ---------------------------------------------------------------------------
# Failure path — _persist_taxpayer_failure invokes mapper + truncates technical
# ---------------------------------------------------------------------------

def test_persist_taxpayer_failure_search_service_dropdown_clicked_maps_arca_slow(
    app,
) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)
    payload = dict(job.payload or {})

    user_es, tech_combined = _persist_taxpayer_failure(
        job.id,
        payload,
        taxpayer_id=taxpayer.id,
        phase=ExtractionPhase.SEARCH_SERVICE,
        error_type="timeout",
        dropdown_clicked=True,
        exception_text="TimeoutError: Timeout 30000ms exceeded",
    )

    expected_user = "ARCA está respondiendo lento, reintentá en unos minutos."
    assert user_es == expected_user
    assert tech_combined.startswith("ARCA_SLOW_AFTER_DROPDOWN | ")

    # Per-client mirror was populated.
    clients = (payload.get("progress") or {}).get("clients") or []
    assert clients[0]["failure_phase"] == ExtractionPhase.SEARCH_SERVICE.value
    assert clients[0]["failure_message_user"] == expected_user
    assert clients[0]["failure_message_technical"].startswith(
        "ARCA_SLOW_AFTER_DROPDOWN | "
    )


def test_persist_taxpayer_failure_truncates_technical_to_1003_chars(app) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)
    payload = dict(job.payload or {})

    huge_exception = "x" * 5000

    _user_es, tech_combined = _persist_taxpayer_failure(
        job.id,
        payload,
        taxpayer_id=taxpayer.id,
        phase=ExtractionPhase.SEARCH_SERVICE,
        error_type="timeout",
        dropdown_clicked=True,
        exception_text=huge_exception,
    )

    # _truncate cuts >1000 chars to text[:1000] + "..."  → max length 1003.
    assert len(tech_combined) == 1003
    assert tech_combined.endswith("...")


def test_persist_taxpayer_failure_phase_none_passes_through(app) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)
    payload = dict(job.payload or {})

    user_es, tech_combined = _persist_taxpayer_failure(
        job.id,
        payload,
        taxpayer_id=taxpayer.id,
        phase=None,
        error_type="unknown",
        dropdown_clicked=False,
        exception_text=None,
    )

    # UNKNOWN_ERROR mapping with no exception text → tech is just the code.
    assert tech_combined == "UNKNOWN_ERROR"
    assert "No pudimos completar la extracción" in user_es

    clients = (payload.get("progress") or {}).get("clients") or []
    assert clients[0]["failure_phase"] is None
    assert clients[0]["failure_message_user"] == user_es
    assert clients[0]["failure_message_technical"] == "UNKNOWN_ERROR"


# ---------------------------------------------------------------------------
# End-to-end worker test with mocked pipeline
# ---------------------------------------------------------------------------

def test_run_playwright_pipeline_job_emits_on_phase_and_persists(
    app, monkeypatch
) -> None:
    """Drive the full worker entrypoint with a fake pipeline service that
    invokes on_phase + on_taxpayer_finish, then assert that DB rows + payload
    reflect the latest phase for the running taxpayer.
    """
    taxpayer = _create_taxpayer()
    job = _create_job(
        taxpayer.id,
        payload={
            "fecha_desde": "01/01/2026",
            "fecha_hasta": "26/02/2026",
            "headless": True,
        },
    )

    from app.services import lpg_playwright_pipeline as pipeline_module
    from app.workers import playwright_jobs as worker_module

    class FakePipeline:
        def run(
            self,
            *,
            on_taxpayer_start=None,
            on_taxpayer_finish=None,
            on_phase=None,
            **_kwargs: Any,
        ):
            assert on_phase is not None
            assert on_taxpayer_start is not None
            assert on_taxpayer_finish is not None

            tp = Taxpayer.query.get(taxpayer.id)

            on_taxpayer_start(tp)
            on_phase(
                tp,
                ExtractionPhase.LOGIN_START,
                "Ingresando a ARCA con clave fiscal...",
            )
            on_phase(
                tp,
                ExtractionPhase.SEARCH_SERVICE,
                "Buscando el servicio Liquidación primaria de granos...",
            )

            result = pipeline_module.TaxpayerPipelineResult(
                taxpayer_id=tp.id,
                empresa=tp.empresa,
                cuit=tp.cuit,
                cuit_representado=tp.cuit_representado,
                outcome="done",
                total_coes_detectados=5,
                total_coes_nuevos=5,
                total_procesados_ok=5,
                total_procesados_error=0,
            )
            on_taxpayer_finish(result)

            return pipeline_module.PipelineRunResult(
                started_at="2026-05-13T00:00:00",
                finished_at="2026-05-13T00:00:05",
                fecha_desde="01/01/2026",
                fecha_hasta="26/02/2026",
                taxpayers_total=1,
                taxpayers_ok=1,
                taxpayers_partial=0,
                taxpayers_error=0,
                results=[result],
            )

    # Replace the pipeline class as referenced inside the worker module.
    monkeypatch.setattr(worker_module, "LpgPlaywrightPipelineService", FakePipeline)
    # Skip the create_app() + app_context() since the test fixture already
    # gives us a live application context.
    monkeypatch.setattr(
        worker_module, "create_app", lambda *args, **kwargs: app
    )

    worker_module.run_playwright_pipeline_job(
        extraction_job_id=job.id,
        fecha_desde="01/01/2026",
        fecha_hasta="26/02/2026",
        taxpayer_ids=[taxpayer.id],
        timeout_ms=30000,
        type_delay_ms=80,
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "completed"
    # Latest phase emitted for the running taxpayer wins job-level fields.
    assert refreshed.current_phase == ExtractionPhase.SEARCH_SERVICE.value
    assert (
        refreshed.current_message
        == "Buscando el servicio Liquidación primaria de granos..."
    )

    progress = (refreshed.payload or {}).get("progress") or {}
    clients = progress.get("clients") or []
    assert len(clients) == 1
    assert clients[0]["current_phase"] == ExtractionPhase.SEARCH_SERVICE.value


def test_run_playwright_pipeline_job_failure_calls_mapper_and_truncates(
    app, monkeypatch
) -> None:
    """When pipeline produces an outcome="error" result with SEARCH_SERVICE +
    dropdown_clicked + timeout, the worker must invoke the failure mapper and
    persist the truncated technical message + per-client failure fields.
    """
    taxpayer = _create_taxpayer()
    job = _create_job(
        taxpayer.id,
        payload={
            "fecha_desde": "01/01/2026",
            "fecha_hasta": "26/02/2026",
            "headless": True,
        },
    )

    from app.services import lpg_playwright_pipeline as pipeline_module
    from app.workers import playwright_jobs as worker_module

    huge_error = "Timeout 30000ms exceeded " + ("x" * 5000)

    class FakePipeline:
        def run(
            self,
            *,
            on_taxpayer_start=None,
            on_taxpayer_finish=None,
            on_phase=None,
            **_kwargs: Any,
        ):
            tp = Taxpayer.query.get(taxpayer.id)
            on_taxpayer_start(tp)
            on_phase(
                tp,
                ExtractionPhase.SEARCH_SERVICE,
                "Buscando el servicio Liquidación primaria de granos...",
            )
            result = pipeline_module.TaxpayerPipelineResult(
                taxpayer_id=tp.id,
                empresa=tp.empresa,
                cuit=tp.cuit,
                cuit_representado=tp.cuit_representado,
                outcome="error",
                error=huge_error,
                failure_phase=ExtractionPhase.SEARCH_SERVICE,
                failure_error_type="timeout",
                failure_dropdown_clicked=True,
            )
            on_taxpayer_finish(result)
            return pipeline_module.PipelineRunResult(
                started_at="2026-05-13T00:00:00",
                finished_at="2026-05-13T00:00:05",
                fecha_desde="01/01/2026",
                fecha_hasta="26/02/2026",
                taxpayers_total=1,
                taxpayers_ok=0,
                taxpayers_partial=0,
                taxpayers_error=1,
                results=[result],
            )

    monkeypatch.setattr(worker_module, "LpgPlaywrightPipelineService", FakePipeline)
    monkeypatch.setattr(
        worker_module, "create_app", lambda *args, **kwargs: app
    )

    worker_module.run_playwright_pipeline_job(
        extraction_job_id=job.id,
        fecha_desde="01/01/2026",
        fecha_hasta="26/02/2026",
        taxpayer_ids=[taxpayer.id],
        timeout_ms=30000,
        type_delay_ms=80,
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "failed"
    # Job-level failure_message_user is the ARCA_SLOW_AFTER_DROPDOWN wording.
    expected_user = "ARCA está respondiendo lento, reintentá en unos minutos."
    assert refreshed.failure_message_user == expected_user
    assert refreshed.failure_phase == ExtractionPhase.SEARCH_SERVICE.value
    # Technical message contains the tech code AND is truncated.
    assert refreshed.failure_message_technical is not None
    assert refreshed.failure_message_technical.startswith(
        "ARCA_SLOW_AFTER_DROPDOWN | "
    )
    assert len(refreshed.failure_message_technical) <= 1003

    # Per-client mirror has the same data.
    progress = (refreshed.payload or {}).get("progress") or {}
    clients = progress.get("clients") or []
    assert len(clients) == 1
    assert clients[0]["failure_phase"] == ExtractionPhase.SEARCH_SERVICE.value
    assert clients[0]["failure_message_user"] == expected_user
    assert clients[0]["failure_message_technical"].startswith(
        "ARCA_SLOW_AFTER_DROPDOWN | "
    )


def test_run_playwright_pipeline_job_clears_stale_failure_fields_on_running(
    app, monkeypatch
) -> None:
    """A previously failed job that gets re-enqueued by RQ must have its 5
    new fields cleared by the worker before any new phase is emitted.
    """
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)
    job.current_phase = "DOWNLOADING_COE"
    job.current_message = "stale message"
    job.failure_phase = "SEARCH_SERVICE"
    job.failure_message_user = "stale user es"
    job.failure_message_technical = "stale tech"
    job.status = "failed"
    db.session.commit()
    stale_seen: dict[str, Any] = {}

    from app.services import lpg_playwright_pipeline as pipeline_module
    from app.workers import playwright_jobs as worker_module

    class FakePipeline:
        def run(self, **_kwargs: Any):
            # Snapshot the job fields immediately AFTER worker sets running
            # and BEFORE any new phase is emitted.
            db.session.expire_all()
            snapshot = ExtractionJob.query.get(job.id)
            stale_seen["current_phase"] = snapshot.current_phase
            stale_seen["current_message"] = snapshot.current_message
            stale_seen["failure_phase"] = snapshot.failure_phase
            stale_seen["failure_message_user"] = snapshot.failure_message_user
            stale_seen["failure_message_technical"] = snapshot.failure_message_technical
            stale_seen["status"] = snapshot.status

            return pipeline_module.PipelineRunResult(
                started_at="2026-05-13T00:00:00",
                finished_at="2026-05-13T00:00:01",
                fecha_desde="01/01/2026",
                fecha_hasta="26/02/2026",
                taxpayers_total=0,
                taxpayers_ok=0,
                taxpayers_partial=0,
                taxpayers_error=0,
                results=[],
            )

    monkeypatch.setattr(worker_module, "LpgPlaywrightPipelineService", FakePipeline)
    monkeypatch.setattr(
        worker_module, "create_app", lambda *args, **kwargs: app
    )

    worker_module.run_playwright_pipeline_job(
        extraction_job_id=job.id,
        fecha_desde="01/01/2026",
        fecha_hasta="26/02/2026",
        taxpayer_ids=[taxpayer.id],
        timeout_ms=30000,
        type_delay_ms=80,
    )

    assert stale_seen["status"] == "running"
    assert stale_seen["current_phase"] is None
    assert stale_seen["current_message"] is None
    assert stale_seen["failure_phase"] is None
    assert stale_seen["failure_message_user"] is None
    assert stale_seen["failure_message_technical"] is None


# ---------------------------------------------------------------------------
# Final job status — completed / failed / partial transitions
# ---------------------------------------------------------------------------

def _run_pipeline_with_results(
    *,
    app,
    monkeypatch,
    job_id: int,
    taxpayer_ids: list[int],
    taxpayers_ok: int,
    taxpayers_error: int,
    results: list[Any],
    taxpayers_partial: int = 0,
) -> None:
    from app.services import lpg_playwright_pipeline as pipeline_module
    from app.workers import playwright_jobs as worker_module

    class FakePipeline:
        def run(
            self,
            *,
            on_taxpayer_start=None,
            on_taxpayer_finish=None,
            on_phase=None,
            **_kwargs: Any,
        ):
            for r in results:
                tp = Taxpayer.query.get(r.taxpayer_id)
                if on_taxpayer_start is not None and tp is not None:
                    on_taxpayer_start(tp)
                if on_taxpayer_finish is not None:
                    on_taxpayer_finish(r)
            return pipeline_module.PipelineRunResult(
                started_at="2026-05-13T00:00:00",
                finished_at="2026-05-13T00:00:05",
                fecha_desde="01/01/2026",
                fecha_hasta="26/02/2026",
                taxpayers_total=len(results),
                taxpayers_ok=taxpayers_ok,
                taxpayers_partial=taxpayers_partial,
                taxpayers_error=taxpayers_error,
                results=results,
            )

    monkeypatch.setattr(worker_module, "LpgPlaywrightPipelineService", FakePipeline)
    monkeypatch.setattr(worker_module, "create_app", lambda *args, **kwargs: app)

    worker_module.run_playwright_pipeline_job(
        extraction_job_id=job_id,
        fecha_desde="01/01/2026",
        fecha_hasta="26/02/2026",
        taxpayer_ids=taxpayer_ids,
        timeout_ms=30000,
        type_delay_ms=80,
    )


def _ok_result(taxpayer: Taxpayer) -> Any:
    from app.services import lpg_playwright_pipeline as pipeline_module

    return pipeline_module.TaxpayerPipelineResult(
        taxpayer_id=taxpayer.id,
        empresa=taxpayer.empresa,
        cuit=taxpayer.cuit,
        cuit_representado=taxpayer.cuit_representado,
        outcome="done",
        total_coes_detectados=2,
        total_coes_nuevos=2,
        total_procesados_ok=2,
        total_procesados_error=0,
    )


def _error_result(taxpayer: Taxpayer) -> Any:
    from app.services import lpg_playwright_pipeline as pipeline_module

    return pipeline_module.TaxpayerPipelineResult(
        taxpayer_id=taxpayer.id,
        empresa=taxpayer.empresa,
        cuit=taxpayer.cuit,
        cuit_representado=taxpayer.cuit_representado,
        outcome="error",
        error="Timeout 30000ms exceeded",
        failure_phase=ExtractionPhase.SEARCH_SERVICE,
        failure_error_type="timeout",
        failure_dropdown_clicked=True,
    )


def _partial_result(taxpayer: Taxpayer) -> Any:
    """Cliente con 7 COEs OK y 1 COE con error a nivel WS (caso del job #14)."""
    from app.services import lpg_playwright_pipeline as pipeline_module

    return pipeline_module.TaxpayerPipelineResult(
        taxpayer_id=taxpayer.id,
        empresa=taxpayer.empresa,
        cuit=taxpayer.cuit,
        cuit_representado=taxpayer.cuit_representado,
        outcome="partial",
        error="Se detectaron errores en liquidacionXCoeConsultar.",
        total_coes_detectados=8,
        total_coes_nuevos=8,
        total_procesados_ok=7,
        total_procesados_error=1,
        failure_phase=ExtractionPhase.SAVING_TO_WS,
        failure_error_type="unknown",
        failure_dropdown_clicked=False,
    )


def test_run_playwright_pipeline_job_all_ok_sets_status_completed(
    app, monkeypatch
) -> None:
    t1 = _create_taxpayer(cuit="20111111111", empresa="Empresa Uno")
    t2 = _create_taxpayer(cuit="20222222222", empresa="Empresa Dos")
    job = _create_job(t1.id)

    _run_pipeline_with_results(
        app=app,
        monkeypatch=monkeypatch,
        job_id=job.id,
        taxpayer_ids=[t1.id, t2.id],
        taxpayers_ok=2,
        taxpayers_error=0,
        results=[_ok_result(t1), _ok_result(t2)],
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "completed"
    assert refreshed.error_message is None
    assert refreshed.failure_phase is None
    assert refreshed.failure_message_user is None
    assert refreshed.failure_message_technical is None


def test_run_playwright_pipeline_job_all_error_sets_status_failed(
    app, monkeypatch
) -> None:
    t1 = _create_taxpayer(cuit="20111111111", empresa="Empresa Uno")
    t2 = _create_taxpayer(cuit="20222222222", empresa="Empresa Dos")
    job = _create_job(t1.id)

    _run_pipeline_with_results(
        app=app,
        monkeypatch=monkeypatch,
        job_id=job.id,
        taxpayer_ids=[t1.id, t2.id],
        taxpayers_ok=0,
        taxpayers_error=2,
        results=[_error_result(t1), _error_result(t2)],
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "failed"
    assert refreshed.error_message is not None
    assert "No se pudo procesar ningún cliente" in refreshed.error_message
    assert refreshed.failure_phase == ExtractionPhase.SEARCH_SERVICE.value
    assert refreshed.failure_message_user is not None
    assert refreshed.failure_message_technical is not None


def test_run_playwright_pipeline_job_mixed_results_sets_status_partial(
    app, monkeypatch
) -> None:
    t1 = _create_taxpayer(cuit="20111111111", empresa="Empresa Uno")
    t2 = _create_taxpayer(cuit="20222222222", empresa="Empresa Dos")
    job = _create_job(t1.id)

    _run_pipeline_with_results(
        app=app,
        monkeypatch=monkeypatch,
        job_id=job.id,
        taxpayer_ids=[t1.id, t2.id],
        taxpayers_ok=1,
        taxpayers_error=1,
        results=[_ok_result(t1), _error_result(t2)],
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "partial"
    assert refreshed.error_message is not None
    assert "Algunos clientes no pudieron procesarse" in refreshed.error_message
    assert "Revisá el detalle por cliente" in refreshed.error_message
    # Partial inherits last_taxpayer_failure info so the user has at least one
    # hint of what went wrong.
    assert refreshed.failure_phase == ExtractionPhase.SEARCH_SERVICE.value
    assert refreshed.failure_message_user is not None
    assert refreshed.failure_message_technical is not None
    assert refreshed.finished_at is not None


def test_run_playwright_pipeline_job_zero_taxpayers_stays_completed(
    app, monkeypatch
) -> None:
    t1 = _create_taxpayer(cuit="20111111111", empresa="Empresa Uno")
    job = _create_job(t1.id)

    _run_pipeline_with_results(
        app=app,
        monkeypatch=monkeypatch,
        job_id=job.id,
        taxpayer_ids=[t1.id],
        taxpayers_ok=0,
        taxpayers_error=0,
        results=[],
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "completed"
    assert refreshed.error_message is None


def test_run_playwright_pipeline_job_partial_coe_level_sets_partial_status(
    app, monkeypatch
) -> None:
    """Caso real job #14: un único cliente con 7 COEs OK + 1 COE con error
    a nivel WS. El cliente queda outcome='partial' y el job en status='partial'.
    """
    t1 = _create_taxpayer(cuit="20111111111", empresa="El Socorro SRL")
    job = _create_job(t1.id)

    _run_pipeline_with_results(
        app=app,
        monkeypatch=monkeypatch,
        job_id=job.id,
        taxpayer_ids=[t1.id],
        taxpayers_ok=0,
        taxpayers_partial=1,
        taxpayers_error=0,
        results=[_partial_result(t1)],
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "partial"
    assert refreshed.error_message is not None
    assert "Algunos clientes no pudieron procesarse" in refreshed.error_message
    # El partial poblá last_taxpayer_failure con la phase del COE que falló.
    assert refreshed.failure_phase == ExtractionPhase.SAVING_TO_WS.value
    assert refreshed.failure_message_user is not None
    assert refreshed.failure_message_technical is not None
    # Per-client mirror: status="partial" con métricas reales.
    progress = (refreshed.payload or {}).get("progress") or {}
    clients = progress.get("clients") or []
    assert len(clients) == 1
    assert clients[0]["status"] == "partial"
    assert clients[0]["metrics"]["total_procesados_ok"] == 7
    assert clients[0]["metrics"]["total_procesados_error"] == 1


def test_run_playwright_pipeline_job_one_done_one_partial_sets_partial(
    app, monkeypatch
) -> None:
    """Dos clientes: uno done, otro partial. El job queda en 'partial'."""
    t1 = _create_taxpayer(cuit="20111111111", empresa="Empresa Uno")
    t2 = _create_taxpayer(cuit="20222222222", empresa="Empresa Dos")
    job = _create_job(t1.id)

    _run_pipeline_with_results(
        app=app,
        monkeypatch=monkeypatch,
        job_id=job.id,
        taxpayer_ids=[t1.id, t2.id],
        taxpayers_ok=1,
        taxpayers_partial=1,
        taxpayers_error=0,
        results=[_ok_result(t1), _partial_result(t2)],
    )

    db.session.expire_all()
    refreshed = ExtractionJob.query.get(job.id)
    assert refreshed.status == "partial"
    assert refreshed.error_message is not None
    assert "Algunos clientes no pudieron procesarse" in refreshed.error_message
    assert refreshed.failure_phase == ExtractionPhase.SAVING_TO_WS.value
    assert refreshed.failure_message_user is not None
