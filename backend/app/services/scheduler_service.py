"""Scheduler service: evalúa qué taxpayers matchean día/hora y encola jobs.

Forma parte del PR5 del plan v2 (§5.1). El worker dedicado que invoca
`tick_scheduler()` en loop, y el hook que actualiza
`scheduler_ultimo_ok` / `scheduler_ultimo_error`, se agregan en PR6.
"""
from __future__ import annotations

import logging

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
    rq_job = queue.enqueue(
        run_playwright_pipeline_job,
        extraction_job_id=job.id,
        **enqueue_kwargs,
    )

    job.payload = {
        **(job.payload or {}),
        "queue_name": queue.name,
        "rq_job_id": rq_job.id,
    }
    db.session.commit()

    logger.info(
        "SCHEDULER_DISPARO | taxpayer_id=%s job_id=%s operation=%s queue=%s rq_job_id=%s",
        taxpayer.id,
        job.id,
        SCHEDULER_OPERATION,
        queue.name,
        rq_job.id,
    )
    return job
