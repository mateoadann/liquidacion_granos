"""Tests para el hook `_actualizar_scheduler_status` en playwright_jobs.

El hook actualiza `Taxpayer.scheduler_ultimo_ok` / `scheduler_ultimo_error` /
`scheduler_ultimo_error_en` solo si el ExtractionJob viene del scheduler
(operation que arranca con "scheduler_"). El manual run NO toca esas columnas.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models import ExtractionJob, Taxpayer
from app.workers.playwright_jobs import (
    SCHEDULER_ERROR_MAX_LEN,
    _actualizar_scheduler_status,
)


def _create_taxpayer(**overrides) -> Taxpayer:
    base = {
        "cuit": "20111111111",
        "empresa": "Test SA",
        "cuit_representado": "30711165378",
        "activo": True,
        "scheduler_activo": True,
        "scheduler_dias_semana": "lun,mar,mie,jue,vie",
        "scheduler_hora_local": "09:00",
        "playwright_enabled": True,
        "clave_fiscal_encrypted": "test",
    }
    base.update(overrides)
    item = Taxpayer(**base)
    db.session.add(item)
    db.session.commit()
    return item


def _create_job(taxpayer: Taxpayer, operation: str, status: str = "pending") -> ExtractionJob:
    job = ExtractionJob(
        taxpayer_id=taxpayer.id,
        operation=operation,
        status=status,
    )
    db.session.add(job)
    db.session.commit()
    return job


def test_worker_actualiza_scheduler_ultimo_ok_si_operation_es_scheduler(app):
    with app.app_context():
        tp = _create_taxpayer(
            cuit="20111111110",
            scheduler_ultimo_error="error previo",
            scheduler_ultimo_error_en=datetime(2026, 1, 1, 12, 0, 0),
        )
        job = _create_job(tp, "scheduler_lpg_extract")

        _actualizar_scheduler_status(job, final_status="completed", error_text=None)

        db.session.refresh(tp)
        assert tp.scheduler_ultimo_ok is not None
        # Limpia el error previo al haber un OK
        assert tp.scheduler_ultimo_error is None
        assert tp.scheduler_ultimo_error_en is None


def test_worker_actualiza_scheduler_ultimo_ok_si_status_es_partial(app):
    """`partial` tambien se considera exito desde el punto de vista del
    scheduler: el job avanzo, algunos clientes salieron OK."""
    with app.app_context():
        tp = _create_taxpayer(cuit="20111111120")
        job = _create_job(tp, "scheduler_lpg_extract")

        _actualizar_scheduler_status(job, final_status="partial", error_text=None)

        db.session.refresh(tp)
        assert tp.scheduler_ultimo_ok is not None
        assert tp.scheduler_ultimo_error is None


def test_worker_actualiza_scheduler_ultimo_error_si_fase_falla(app):
    with app.app_context():
        tp = _create_taxpayer(cuit="20111111112")
        job = _create_job(tp, "scheduler_lpg_extract")

        _actualizar_scheduler_status(
            job, final_status="failed", error_text="ARCA timeout"
        )

        db.session.refresh(tp)
        assert tp.scheduler_ultimo_error == "ARCA timeout"
        assert tp.scheduler_ultimo_error_en is not None
        # No tocamos scheduler_ultimo_ok: si habia uno previo, sigue ahi.
        assert tp.scheduler_ultimo_ok is None


def test_worker_NO_toca_scheduler_si_operation_no_es_scheduler(app):
    """`/playwright/lpg/run` manual usa operation 'playwright_lpg_run'; no
    debe escribir en las columnas scheduler_*."""
    with app.app_context():
        tp = _create_taxpayer(cuit="20111111113")
        job = _create_job(tp, "playwright_lpg_run")

        _actualizar_scheduler_status(job, final_status="completed", error_text=None)

        db.session.refresh(tp)
        assert tp.scheduler_ultimo_ok is None
        assert tp.scheduler_ultimo_error is None
        assert tp.scheduler_ultimo_error_en is None


def test_worker_trunca_error_message_a_1000_chars(app):
    with app.app_context():
        tp = _create_taxpayer(cuit="20111111114")
        job = _create_job(tp, "scheduler_run_now")

        mensaje_largo = "x" * 3000
        _actualizar_scheduler_status(
            job, final_status="failed", error_text=mensaje_largo
        )

        db.session.refresh(tp)
        assert tp.scheduler_ultimo_error is not None
        assert len(tp.scheduler_ultimo_error) == SCHEDULER_ERROR_MAX_LEN
        assert tp.scheduler_ultimo_error == "x" * SCHEDULER_ERROR_MAX_LEN


def test_worker_hook_tolera_job_sin_operation(app):
    """Seguridad: si por alguna razon el job no tiene operation, no rompe."""
    with app.app_context():
        tp = _create_taxpayer(cuit="20111111115")
        # Instancia transient (no persistida) con operation=None para
        # evitar el constraint NOT NULL de la DB; solo testeamos la rama.
        job = ExtractionJob(taxpayer_id=tp.id, operation=None, status="pending")

        _actualizar_scheduler_status(job, final_status="completed", error_text=None)

        db.session.refresh(tp)
        assert tp.scheduler_ultimo_ok is None


def test_worker_hook_usa_default_error_si_text_vacio(app):
    """Si la excepcion no aporta texto (str(exc) vacio), igual queremos
    registrar algo para que el admin sepa que hubo falla."""
    with app.app_context():
        tp = _create_taxpayer(cuit="20111111116")
        job = _create_job(tp, "scheduler_lpg_extract")

        _actualizar_scheduler_status(job, final_status="failed", error_text="")

        db.session.refresh(tp)
        assert tp.scheduler_ultimo_error == "Falla desconocida"
        assert tp.scheduler_ultimo_error_en is not None
