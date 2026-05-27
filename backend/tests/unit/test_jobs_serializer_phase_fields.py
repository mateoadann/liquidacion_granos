from __future__ import annotations

import pytest

from app.api.jobs import _serialize_job as _serialize_job_jobs
from app.api.playwright import _serialize_job as _serialize_job_playwright
from app.extensions import db
from app.models import ExtractionJob, Taxpayer

_PHASE_FIELDS = (
    "current_phase",
    "current_message",
    "failure_phase",
    "failure_message_user",
    "failure_message_technical",
    "failure_error_type",
)


def _create_taxpayer() -> Taxpayer:
    item = Taxpayer()
    item.cuit = "20111111111"
    item.empresa = "Empresa Uno"
    item.cuit_representado = "20111111111"
    item.clave_fiscal_encrypted = "test"
    item.playwright_enabled = True
    item.activo = True
    db.session.add(item)
    db.session.commit()
    return item


def _create_job(
    taxpayer_id: int,
    *,
    current_phase: str | None = None,
    current_message: str | None = None,
    failure_phase: str | None = None,
    failure_message_user: str | None = None,
    failure_message_technical: str | None = None,
    failure_error_type: str | None = None,
) -> ExtractionJob:
    item = ExtractionJob()
    item.taxpayer_id = taxpayer_id
    item.operation = "playwright_lpg_run"
    item.status = "running"
    item.current_phase = current_phase
    item.current_message = current_message
    item.failure_phase = failure_phase
    item.failure_message_user = failure_message_user
    item.failure_message_technical = failure_message_technical
    item.failure_error_type = failure_error_type
    db.session.add(item)
    db.session.commit()
    return item


# ---------------------------------------------------------------------------
# Both serializers expose all 5 new keys
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "serializer",
    [_serialize_job_jobs, _serialize_job_playwright],
    ids=["jobs._serialize_job", "playwright._serialize_job"],
)
def test_serializer_exposes_phase_fields_with_values(app, serializer) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(
        taxpayer.id,
        current_phase="SEARCH_SERVICE",
        current_message="Buscando el servicio Liquidación primaria de granos...",
        failure_phase="LOGIN_START",
        failure_message_user="Clave fiscal vencida.",
        failure_message_technical="AUTH_FAILED at login | Exception(...)",
        failure_error_type="auth_failed",
    )

    payload = serializer(job)

    for key in _PHASE_FIELDS:
        assert key in payload, f"missing key {key}"

    assert payload["current_phase"] == "SEARCH_SERVICE"
    assert (
        payload["current_message"]
        == "Buscando el servicio Liquidación primaria de granos..."
    )
    assert payload["failure_phase"] == "LOGIN_START"
    assert payload["failure_message_user"] == "Clave fiscal vencida."
    assert payload["failure_message_technical"] == "AUTH_FAILED at login | Exception(...)"
    assert payload["failure_error_type"] == "auth_failed"


@pytest.mark.parametrize(
    "serializer",
    [_serialize_job_jobs, _serialize_job_playwright],
    ids=["jobs._serialize_job", "playwright._serialize_job"],
)
def test_serializer_returns_none_for_unset_phase_fields(app, serializer) -> None:
    taxpayer = _create_taxpayer()
    job = _create_job(taxpayer.id)  # all phase fields default to None

    payload = serializer(job)

    for key in _PHASE_FIELDS:
        assert key in payload, f"missing key {key} when value is None"
        assert payload[key] is None, f"{key} expected None, got {payload[key]!r}"
