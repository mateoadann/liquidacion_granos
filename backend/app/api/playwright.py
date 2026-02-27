from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import ExtractionJob, Taxpayer
from ..queue import get_queue
from ..time_utils import now_cordoba_naive

playwright_bp = Blueprint("playwright", __name__)
logger = logging.getLogger(__name__)

PLAYWRIGHT_OPERATION = "playwright_lpg_run"
ALLOWED_JOB_STATUS = {"pending", "running", "completed", "failed"}


def _error(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def _serialize_job(item: ExtractionJob) -> dict:
    return {
        "id": item.id,
        "operation": item.operation,
        "status": item.status,
        "payload": item.payload,
        "result": item.result,
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _parse_date(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} es obligatorio (DD/MM/AAAA).")
    text = value.strip()
    try:
        parsed = datetime.strptime(text, "%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(
            f"{field} inválida: '{text}'. Formato esperado DD/MM/AAAA."
        ) from exc
    return parsed.strftime("%d/%m/%Y")


def _parse_int_list(field: str, value: object | None) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field} debe ser una lista de enteros.")
    result: list[int] = []
    seen: set[int] = set()
    for item in value:
        if not isinstance(item, int):
            raise ValueError(f"{field} debe contener solo enteros.")
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _parse_and_validate_run_payload(payload: dict) -> tuple[str, str, list[int] | None, int, int]:
    fecha_desde = _parse_date("fecha_desde", payload.get("fecha_desde"))
    fecha_hasta = _parse_date("fecha_hasta", payload.get("fecha_hasta"))
    taxpayer_ids = _parse_int_list("taxpayer_ids", payload.get("taxpayer_ids"))
    timeout_ms = int(payload.get("timeout_ms", 30000))
    type_delay_ms = int(payload.get("type_delay_ms", 80))

    if timeout_ms <= 0:
        raise ValueError("timeout_ms debe ser mayor a 0.")
    if type_delay_ms < 0:
        raise ValueError("type_delay_ms no puede ser negativo.")

    return fecha_desde, fecha_hasta, taxpayer_ids, timeout_ms, type_delay_ms


@playwright_bp.post("/playwright/lpg/run")
def enqueue_lpg_playwright_pipeline():
    payload = request.get_json(silent=True) or {}
    try:
        fecha_desde, fecha_hasta, taxpayer_ids, timeout_ms, type_delay_ms = (
            _parse_and_validate_run_payload(payload)
        )
    except ValueError as exc:
        return _error(str(exc), 400)

    try:
        from ..workers.playwright_jobs import run_playwright_pipeline_job
    except ModuleNotFoundError as exc:
        if exc.name == "playwright":
            return _error(
                (
                    "Playwright no está instalado en backend. "
                    "Instalar con pip y playwright install chromium."
                ),
                503,
            )
        raise

    logger.info(
        "JOB_RECEIVED | operation=%s desde=%s hasta=%s taxpayers=%s timeout_ms=%s type_delay_ms=%s",
        PLAYWRIGHT_OPERATION,
        fecha_desde,
        fecha_hasta,
        taxpayer_ids or "todos",
        timeout_ms,
        type_delay_ms,
    )

    if taxpayer_ids:
        existing_ids = {
            item.id
            for item in Taxpayer.query.filter(Taxpayer.id.in_(taxpayer_ids)).with_entities(Taxpayer.id)
        }
        missing = [item for item in taxpayer_ids if item not in existing_ids]
        if missing:
            return _error(f"taxpayer_ids inexistentes: {missing}", 400)
        anchor_taxpayer_id = taxpayer_ids[0]
    else:
        anchor_taxpayer = (
            Taxpayer.query.filter(
                Taxpayer.activo.is_(True), Taxpayer.playwright_enabled.is_(True)
            )
            .order_by(Taxpayer.id.asc())
            .first()
        )
        if not anchor_taxpayer:
            return _error("No hay clientes activos con Playwright habilitado.", 400)
        anchor_taxpayer_id = anchor_taxpayer.id

    item = ExtractionJob()
    item.taxpayer_id = anchor_taxpayer_id
    item.operation = PLAYWRIGHT_OPERATION
    item.status = "pending"
    item.payload = {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "taxpayer_ids": taxpayer_ids,
        "timeout_ms": timeout_ms,
        "type_delay_ms": type_delay_ms,
        "headless": True,
    }
    db.session.add(item)
    db.session.commit()

    try:
        queue = get_queue("playwright")
        rq_job = queue.enqueue(
            run_playwright_pipeline_job,
            extraction_job_id=item.id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            taxpayer_ids=taxpayer_ids,
            timeout_ms=timeout_ms,
            type_delay_ms=type_delay_ms,
            job_timeout=max((timeout_ms // 1000) * 10, 3600),
            result_ttl=86400,
            failure_ttl=86400,
        )
    except Exception as exc:
        item.status = "failed"
        item.error_message = f"No se pudo encolar el job Playwright: {exc}"
        item.finished_at = now_cordoba_naive()
        db.session.commit()
        logger.exception(
            "JOB_ENQUEUE_FAILED | job_id=%s operation=%s error=%s",
            item.id,
            PLAYWRIGHT_OPERATION,
            exc,
        )
        return _error(
            "No se pudo encolar el job Playwright. Verificá Redis/worker e intentá nuevamente.",
            503,
        )

    item.payload = {
        **(item.payload or {}),
        "queue_name": queue.name,
        "rq_job_id": rq_job.id,
    }
    db.session.commit()

    logger.info(
        "JOB_ENQUEUED | job_id=%s operation=%s queue=%s rq_job_id=%s",
        item.id,
        PLAYWRIGHT_OPERATION,
        queue.name,
        rq_job.id,
    )
    return (
        jsonify(
            {
                "message": "Proceso Playwright encolado.",
                "job": _serialize_job(item),
            }
        ),
        202,
    )


@playwright_bp.get("/playwright/lpg/jobs/<int:job_id>")
def get_lpg_playwright_job(job_id: int):
    item = ExtractionJob.query.get_or_404(job_id)
    if item.operation != PLAYWRIGHT_OPERATION:
        return _error("job_id no corresponde a una corrida Playwright LPG.", 404)
    if item.status not in ALLOWED_JOB_STATUS:
        item.status = "failed"
        item.error_message = item.error_message or "Estado de job inválido."
        db.session.commit()
    return jsonify(_serialize_job(item))
