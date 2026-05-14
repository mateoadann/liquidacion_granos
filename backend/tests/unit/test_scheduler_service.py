"""Tests unit para app.services.scheduler_service.

Verifican el matching día/hora, el dedup-window de 1h, y la creación del
ExtractionJob + encolado en RQ.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models.extraction_job import ExtractionJob
from app.models.taxpayer import Taxpayer
from app.services import scheduler_service
from app.services.scheduler_service import (
    DEDUP_WINDOW_SECONDS,
    SCHEDULER_OPERATION,
    SCHEDULER_QUEUE_NAME,
    _disparar_extraccion,
    tick_scheduler,
)


# Lunes 2026-05-11 09:00 → weekday()==0 → "lun", hora "09:00"
FIXED_NOW_LUN_0900 = datetime(2026, 5, 11, 9, 0, 0)
# Sábado 2026-05-16 09:00 → weekday()==5 → "sab"
FIXED_NOW_SAB_0900 = datetime(2026, 5, 16, 9, 0, 0)


_CUIT_COUNTER = {"value": 20_111_111_110}


def _next_cuit() -> str:
    _CUIT_COUNTER["value"] += 1
    return str(_CUIT_COUNTER["value"])


def _create_taxpayer(**kwargs) -> Taxpayer:
    defaults = {
        "cuit": _next_cuit(),
        "empresa": "Test SA",
        "cuit_representado": "30711165378",
        "activo": True,
        "scheduler_activo": True,
        "scheduler_dias_semana": "lun,mar,mie,jue,vie",
        "scheduler_hora_local": "09:00",
    }
    defaults.update(kwargs)
    tp = Taxpayer(**defaults)
    db.session.add(tp)
    db.session.commit()
    return tp


@pytest.fixture(autouse=True)
def _patch_queue():
    """Mockea get_queue en TODOS los tests para no requerir Redis real."""
    with patch(
        "app.services.scheduler_service.get_queue"
    ) as mock_get_queue:
        fake_queue = MagicMock()
        fake_queue.enqueue.return_value = MagicMock(id="rq-job-fake")
        mock_get_queue.return_value = fake_queue
        yield mock_get_queue


@pytest.fixture(autouse=True)
def _patch_worker_import():
    """Evita que el import de playwright_jobs falle si playwright no está instalado."""
    with patch.dict(
        "sys.modules",
        {
            "app.workers.playwright_jobs": MagicMock(
                run_playwright_pipeline_job=MagicMock()
            ),
        },
    ):
        yield


def _patch_now(value: datetime):
    return patch(
        "app.services.scheduler_service.now_cordoba_naive",
        return_value=value,
    )


def test_tick_ignora_taxpayers_con_activo_false(app):
    with app.app_context():
        _create_taxpayer(activo=False)
        with _patch_now(FIXED_NOW_LUN_0900):
            res = tick_scheduler()
        assert res == {"disparados": [], "evaluados": 0}


def test_tick_ignora_taxpayers_con_scheduler_activo_false(app):
    with app.app_context():
        _create_taxpayer(scheduler_activo=False)
        with _patch_now(FIXED_NOW_LUN_0900):
            res = tick_scheduler()
        assert res == {"disparados": [], "evaluados": 0}


def test_tick_ignora_si_dia_no_matchea(app):
    with app.app_context():
        # Taxpayer configurado solo lunes, simulamos sábado
        _create_taxpayer(scheduler_dias_semana="lun")
        with _patch_now(FIXED_NOW_SAB_0900):
            res = tick_scheduler()
        assert res["disparados"] == []
        assert res["evaluados"] == 1


def test_tick_ignora_si_hora_no_matchea(app):
    with app.app_context():
        _create_taxpayer(scheduler_hora_local="07:30")
        with _patch_now(FIXED_NOW_LUN_0900):
            res = tick_scheduler()
        assert res["disparados"] == []
        assert res["evaluados"] == 1


def test_tick_dispara_si_dia_y_hora_matchean(app, _patch_queue):
    with app.app_context():
        tp = _create_taxpayer(
            scheduler_dias_semana="lun,mar",
            scheduler_hora_local="09:00",
        )
        with _patch_now(FIXED_NOW_LUN_0900):
            res = tick_scheduler()
        assert res["disparados"] == [tp.id]
        assert res["evaluados"] == 1
        _patch_queue.return_value.enqueue.assert_called_once()


def test_tick_no_dispara_si_ultimo_ok_fue_hace_menos_de_1h(app, _patch_queue):
    with app.app_context():
        ultimo_ok = FIXED_NOW_LUN_0900 - timedelta(seconds=DEDUP_WINDOW_SECONDS - 60)
        _create_taxpayer(scheduler_ultimo_ok=ultimo_ok)
        with _patch_now(FIXED_NOW_LUN_0900):
            res = tick_scheduler()
        assert res["disparados"] == []
        assert res["evaluados"] == 1
        _patch_queue.return_value.enqueue.assert_not_called()


def test_tick_dispara_si_ultimo_ok_fue_hace_mas_de_1h(app, _patch_queue):
    with app.app_context():
        ultimo_ok = FIXED_NOW_LUN_0900 - timedelta(seconds=DEDUP_WINDOW_SECONDS + 60)
        tp = _create_taxpayer(scheduler_ultimo_ok=ultimo_ok)
        with _patch_now(FIXED_NOW_LUN_0900):
            res = tick_scheduler()
        assert res["disparados"] == [tp.id]
        _patch_queue.return_value.enqueue.assert_called_once()


def test_disparar_extraccion_crea_extraction_job_pending(app):
    with app.app_context():
        tp = _create_taxpayer()
        job = _disparar_extraccion(tp)

        # Refrescar desde DB
        persisted = db.session.get(ExtractionJob, job.id)
        assert persisted is not None
        assert persisted.taxpayer_id == tp.id
        assert persisted.operation == SCHEDULER_OPERATION
        assert persisted.status == "pending"


def test_disparar_extraccion_encola_en_rq(app, _patch_queue):
    with app.app_context():
        tp = _create_taxpayer()
        job = _disparar_extraccion(tp)

        _patch_queue.assert_called_with(SCHEDULER_QUEUE_NAME)
        fake_queue = _patch_queue.return_value
        fake_queue.enqueue.assert_called_once()
        call_kwargs = fake_queue.enqueue.call_args.kwargs
        assert call_kwargs["extraction_job_id"] == job.id
        assert call_kwargs["fecha_desde"] is None
        assert call_kwargs["fecha_hasta"] is None


def test_tick_dispara_uno_por_taxpayer_matcheante(app, _patch_queue):
    with app.app_context():
        tp1 = _create_taxpayer(scheduler_hora_local="09:00")
        tp2 = _create_taxpayer(scheduler_hora_local="09:00")
        # No-match: hora distinta
        _create_taxpayer(scheduler_hora_local="10:00")
        # No-match: scheduler_activo False
        _create_taxpayer(scheduler_activo=False, scheduler_hora_local="09:00")

        with _patch_now(FIXED_NOW_LUN_0900):
            res = tick_scheduler()

        assert sorted(res["disparados"]) == sorted([tp1.id, tp2.id])
        # evaluados cuenta solo los con scheduler_activo=True AND activo=True (3)
        assert res["evaluados"] == 3
        assert _patch_queue.return_value.enqueue.call_count == 2
