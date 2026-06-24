"""Scheduler service: evalúa qué taxpayers matchean día/hora y encola jobs.

Forma parte del PR5 del plan v2 (§5.1). El worker dedicado que invoca
`tick_scheduler()` en loop, y el hook que actualiza
`scheduler_ultimo_ok` / `scheduler_ultimo_error`, se agregan en PR6.
"""
from __future__ import annotations

import logging
import random
from datetime import timedelta
from typing import Optional

from flask import current_app

from ..extensions import db
from ..models.extraction_job import ExtractionJob
from ..models.taxpayer import Taxpayer
from ..queue import get_queue
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)

DIAS_SEMANA = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
DEDUP_WINDOW_SECONDS = 3600  # No re-disparar si último OK fue hace menos de 1h
SCHEDULER_OPERATION = "scheduler_lpg_extract"
SCHEDULER_QUEUE_NAME = "playwright"


def reactivar_pausados_por_auth() -> int:
    """Reactiva clientes pausados automáticamente por AUTH_FAILED cuya clave
    fiscal fue actualizada después del error. Devuelve la cantidad reactivada.

    No toca pausas manuales (scheduler_pausado_por_auth=False).
    """
    candidatos = Taxpayer.query.filter_by(
        scheduler_pausado_por_auth=True, activo=True
    ).all()
    reactivados = 0
    for t in candidatos:
        if (
            t.clave_fiscal_actualizada_en is not None
            and t.scheduler_ultimo_error_en is not None
            and t.clave_fiscal_actualizada_en > t.scheduler_ultimo_error_en
        ):
            t.scheduler_activo = True
            t.scheduler_pausado_por_auth = False
            reactivados += 1
            logger.info(
                "SCHEDULER_AUTO_REACTIVATED | taxpayer_id=%s", t.id
            )
    if reactivados:
        db.session.commit()
    return reactivados


def tick_scheduler() -> dict:
    """Evalúa qué empresas matchean día/hora actual y encola un job para cada una.

    Retorna resumen con `disparados` (lista de taxpayer_ids) y `evaluados` (total).

    Reglas:
    - Solo taxpayers con `scheduler_activo=True` AND `activo=True`.
    - Día de hoy debe estar en `scheduler_dias_semana` (CSV: "lun,mar,mie,jue,vie").
    - Hora actual `HH:MM` debe matchear `scheduler_hora_local` (igualdad estricta).
    - Si `scheduler_ultimo_ok` es de hace menos de DEDUP_WINDOW_SECONDS → skip
      (evita doble-disparo si el tick corre cada minuto pero la hora_local matchea
      por varios ticks).
    """
    reactivar_pausados_por_auth()
    now = now_cordoba_naive()
    dia = DIAS_SEMANA[now.weekday()]
    hora = now.strftime("%H:%M")

    taxpayers = Taxpayer.query.filter_by(
        scheduler_activo=True, activo=True
    ).all()

    disparados: list[int] = []
    for t in taxpayers:
        dias = [d.strip() for d in (t.scheduler_dias_semana or "").split(",") if d.strip()]
        if dia not in dias:
            continue
        if t.scheduler_hora_local != hora:
            continue
        if t.scheduler_ultimo_ok:
            elapsed = (now - t.scheduler_ultimo_ok).total_seconds()
            if elapsed < DEDUP_WINDOW_SECONDS:
                logger.info(
                    "SCHEDULER_SKIP_RECENT | taxpayer_id=%s elapsed=%.0fs",
                    t.id,
                    elapsed,
                )
                continue

        _disparar_extraccion(t)
        disparados.append(t.id)

    return {"disparados": disparados, "evaluados": len(taxpayers)}


def _disparar_extraccion(taxpayer: Taxpayer) -> ExtractionJob:
    """Crea un ExtractionJob y lo encola en RQ para que el worker lo procese.

    El payload persistido refleja los mismos campos que `playwright_lpg_run`
    (fecha_desde/hasta, taxpayer_ids, parámetros de Playwright, retries,
    queue_name, rq_job_id) para que los jobs disparados por scheduler sean
    igual de descriptivos que los manuales.
    """
    from ..workers.playwright_jobs import run_playwright_pipeline_job
    from ..workers.scheduler_defaults import scheduler_enqueue_kwargs

    enqueue_kwargs = scheduler_enqueue_kwargs(
        taxpayer.id,
        dias_extraccion=taxpayer.scheduler_dias_extraccion or 90,
    )

    job = ExtractionJob(
        taxpayer_id=taxpayer.id,
        operation=SCHEDULER_OPERATION,
        status="pending",
    )
    job.payload = {**enqueue_kwargs, "headless": True}
    db.session.add(job)
    db.session.commit()

    queue = get_queue(SCHEDULER_QUEUE_NAME)
    jitter_window = current_app.config["SCHEDULER_JITTER_WINDOW_SECONDS"]
    delay_segundos = random.randint(0, jitter_window)
    rq_job = queue.enqueue_in(
        timedelta(seconds=delay_segundos),
        run_playwright_pipeline_job,
        extraction_job_id=job.id,
        **enqueue_kwargs,
    )

    job.payload = {
        **(job.payload or {}),
        "queue_name": queue.name,
        "rq_job_id": rq_job.id,
        "jitter_delay_seconds": delay_segundos,
    }
    db.session.commit()

    logger.info(
        "SCHEDULER_DISPARO | taxpayer_id=%s job_id=%s operation=%s queue=%s rq_job_id=%s jitter_delay_s=%s",
        taxpayer.id,
        job.id,
        SCHEDULER_OPERATION,
        queue.name,
        rq_job.id,
        delay_segundos,
    )
    return job


def reconcile_stale_jobs(timeout_seconds: Optional[int] = None) -> int:
    """Marca como 'failed' los ExtractionJobs que llevan demasiado tiempo en 'running'.

    Usa `updated_at` como indicador de actividad reciente (el worker lo actualiza
    en cada progreso). Si `updated_at` no existe en el registro, cae a `started_at`
    y luego a `created_at` como referencias de antigüedad.

    Args:
        timeout_seconds: Segundos de inactividad antes de considerar un job colgado.
            Si es None, usa `STALE_JOB_TIMEOUT_SECONDS` de la config de la app
            (default 1800 = 30 min).

    Returns:
        Cantidad de jobs reconciliados (marcados como failed).
    """
    if timeout_seconds is None:
        timeout_seconds = current_app.config.get("STALE_JOB_TIMEOUT_SECONDS", 1800)

    now = now_cordoba_naive()
    threshold = now - timedelta(seconds=timeout_seconds)

    running_jobs: list[ExtractionJob] = ExtractionJob.query.filter_by(
        status="running"
    ).all()

    reconciled = 0
    for job in running_jobs:
        # Use the best available "last activity" timestamp
        last_activity = job.updated_at or job.started_at or job.created_at
        if last_activity is None or last_activity > threshold:
            continue

        elapsed_seconds = int((now - last_activity).total_seconds())
        try:
            job.status = "failed"
            job.finished_at = now
            job.failure_error_type = "stale_timeout"
            job.failure_code = "UNKNOWN_ERROR"
            job.failure_message_user = (
                "Proceso interrumpido: la extracción quedó sin actividad "
                "y se cerró automáticamente."
            )
            job.failure_message_technical = (
                f"Job marcado como stale por el reconciliador. "
                f"Tiempo sin actividad: {elapsed_seconds}s "
                f"(umbral: {timeout_seconds}s). "
                f"Última actividad registrada: {last_activity.isoformat()}."
            )
            db.session.commit()
            reconciled += 1
            logger.warning(
                "RECONCILE_STALE_JOB | job_id=%s taxpayer_id=%s elapsed=%ds threshold=%ds",
                job.id,
                job.taxpayer_id,
                elapsed_seconds,
                timeout_seconds,
            )
        except Exception:
            db.session.rollback()
            logger.exception(
                "RECONCILE_ERROR | job_id=%s — rollback realizado", job.id
            )

    if reconciled:
        logger.warning(
            "RECONCILE_SUMMARY | jobs_reconciliados=%d timeout_s=%d",
            reconciled,
            timeout_seconds,
        )
    else:
        logger.debug(
            "RECONCILE_OK | sin jobs colgados (running evaluados=%d timeout_s=%d)",
            len(running_jobs),
            timeout_seconds,
        )

    return reconciled
