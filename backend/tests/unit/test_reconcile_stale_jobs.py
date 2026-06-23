"""Tests unit para reconcile_stale_jobs (app.services.scheduler_service).

Verifica que:
- Un job running con updated_at más antiguo que el timeout → se marca failed.
- Un job running actualizado recientemente → no se toca.
- Un job completed o failed → no se toca.
- Se retorna el conteo correcto de jobs reconciliados.
- El argumento timeout_seconds personalizado es respetado.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.extraction_job import ExtractionJob
from app.models.taxpayer import Taxpayer
from app.services.scheduler_service import reconcile_stale_jobs

# Fixed "now" used in all tests — a naive Argentina/Cordoba datetime.
FIXED_NOW = datetime(2026, 6, 18, 12, 0, 0)
DEFAULT_TIMEOUT = 1800  # 30 min — same as config default


def _patch_now(value: datetime):
    return patch(
        "app.services.scheduler_service.now_cordoba_naive",
        return_value=value,
    )


# Counter so each test gets a unique CUIT without collisions.
_CUIT_CTR = {"v": 20_200_000_000}


def _next_cuit() -> str:
    _CUIT_CTR["v"] += 1
    return str(_CUIT_CTR["v"])


def _make_taxpayer() -> Taxpayer:
    tp = Taxpayer(
        cuit=_next_cuit(),
        empresa="Test SA",
        cuit_representado=_next_cuit(),
        activo=True,
    )
    db.session.add(tp)
    db.session.flush()  # get tp.id without committing yet
    return tp


def _make_job(taxpayer: Taxpayer, status: str, updated_at: datetime) -> ExtractionJob:
    job = ExtractionJob(
        taxpayer_id=taxpayer.id,
        operation="test_op",
        status=status,
    )
    db.session.add(job)
    db.session.flush()
    # Override updated_at explicitly (bypasses onupdate)
    job.updated_at = updated_at
    db.session.commit()
    return job


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stale_running_job_is_marked_failed(app):
    """A running job whose updated_at is beyond the timeout becomes 'failed'."""
    with app.app_context():
        tp = _make_taxpayer()
        stale_updated_at = FIXED_NOW - timedelta(seconds=DEFAULT_TIMEOUT + 60)
        job = _make_job(tp, "running", stale_updated_at)

        with _patch_now(FIXED_NOW):
            count = reconcile_stale_jobs(timeout_seconds=DEFAULT_TIMEOUT)

        assert count == 1
        db.session.refresh(job)
        assert job.status == "failed"
        assert job.finished_at is not None
        assert job.failure_error_type == "stale_timeout"
        assert job.failure_message_user is not None and len(job.failure_message_user) > 0
        assert job.failure_message_technical is not None


def test_recent_running_job_is_not_touched(app):
    """A running job updated within the timeout window is left alone."""
    with app.app_context():
        tp = _make_taxpayer()
        recent_updated_at = FIXED_NOW - timedelta(seconds=DEFAULT_TIMEOUT - 60)
        job = _make_job(tp, "running", recent_updated_at)

        with _patch_now(FIXED_NOW):
            count = reconcile_stale_jobs(timeout_seconds=DEFAULT_TIMEOUT)

        assert count == 0
        db.session.refresh(job)
        assert job.status == "running"
        assert job.finished_at is None


def test_completed_job_is_not_touched(app):
    """A completed job is never reconciled regardless of timestamps."""
    with app.app_context():
        tp = _make_taxpayer()
        old_dt = FIXED_NOW - timedelta(seconds=DEFAULT_TIMEOUT + 3600)
        job = _make_job(tp, "completed", old_dt)

        with _patch_now(FIXED_NOW):
            count = reconcile_stale_jobs(timeout_seconds=DEFAULT_TIMEOUT)

        assert count == 0
        db.session.refresh(job)
        assert job.status == "completed"


def test_failed_job_is_not_touched(app):
    """A job already in 'failed' status is not reconciled again."""
    with app.app_context():
        tp = _make_taxpayer()
        old_dt = FIXED_NOW - timedelta(seconds=DEFAULT_TIMEOUT + 3600)
        job = _make_job(tp, "failed", old_dt)

        with _patch_now(FIXED_NOW):
            count = reconcile_stale_jobs(timeout_seconds=DEFAULT_TIMEOUT)

        assert count == 0
        db.session.refresh(job)
        assert job.status == "failed"


def test_returns_correct_count_for_multiple_jobs(app):
    """Returns the exact number of jobs marked as stale."""
    with app.app_context():
        tp = _make_taxpayer()
        stale_dt = FIXED_NOW - timedelta(seconds=DEFAULT_TIMEOUT + 120)
        recent_dt = FIXED_NOW - timedelta(seconds=DEFAULT_TIMEOUT - 120)

        _make_job(tp, "running", stale_dt)   # stale #1
        _make_job(tp, "running", stale_dt)   # stale #2
        _make_job(tp, "running", recent_dt)  # not stale
        _make_job(tp, "completed", stale_dt) # terminal — ignored

        with _patch_now(FIXED_NOW):
            count = reconcile_stale_jobs(timeout_seconds=DEFAULT_TIMEOUT)

        assert count == 2


def test_custom_timeout_is_respected(app):
    """A shorter custom timeout marks jobs that would survive the default."""
    with app.app_context():
        tp = _make_taxpayer()
        # 5 minutes old — stale under a 3-min timeout but fine under 30-min default
        updated_at = FIXED_NOW - timedelta(seconds=300)
        job = _make_job(tp, "running", updated_at)

        with _patch_now(FIXED_NOW):
            count = reconcile_stale_jobs(timeout_seconds=180)  # 3 minutes

        assert count == 1
        db.session.refresh(job)
        assert job.status == "failed"


def test_reads_timeout_from_app_config_when_none(app):
    """When timeout_seconds is None, the function reads STALE_JOB_TIMEOUT_SECONDS from config."""
    with app.app_context():
        tp = _make_taxpayer()
        # Use a small config value so the test doesn't need to create a 30-min-old job
        app.config["STALE_JOB_TIMEOUT_SECONDS"] = 120  # 2 minutes
        stale_dt = FIXED_NOW - timedelta(seconds=180)  # 3 minutes old
        job = _make_job(tp, "running", stale_dt)

        with _patch_now(FIXED_NOW):
            count = reconcile_stale_jobs()  # no explicit timeout → reads config

        assert count == 1
        db.session.refresh(job)
        assert job.status == "failed"
