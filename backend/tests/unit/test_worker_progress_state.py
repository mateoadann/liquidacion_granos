"""Tests for service_open_method propagation in the progress dict helpers.

These tests are fast (no Flask app, no DB). _update_job is monkeypatched to a
no-op because the tests only care about in-memory dict mutations.
"""
from __future__ import annotations

import types

import pytest

from app.workers import playwright_jobs
from app.workers.playwright_jobs import _build_progress_payload, _update_progress_state


# ---------------------------------------------------------------------------
# Fixture: silence the DB write so tests remain fast and DB-free
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _silence_update_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(playwright_jobs, "_update_job", lambda *_, **__: None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_taxpayer(taxpayer_id: int, empresa: str = "Empresa SA") -> object:
    """Minimal stub that satisfies _build_progress_payload (uses .id + .empresa)."""
    obj = types.SimpleNamespace(id=taxpayer_id, empresa=empresa)
    return obj


# ---------------------------------------------------------------------------
# Tests for _build_progress_payload
# ---------------------------------------------------------------------------


def test_build_progress_payload_seeds_service_open_method_none() -> None:
    """Every client entry in the initial payload must have service_open_method=None."""
    taxpayers = [_make_taxpayer(1, "Alpha SA"), _make_taxpayer(2, "Beta SRL")]
    payload = _build_progress_payload(taxpayers)  # type: ignore[arg-type]

    clients = payload["clients"]
    assert len(clients) == 2
    for client in clients:
        assert "service_open_method" in client, (
            f"service_open_method missing from client {client.get('taxpayer_id')}"
        )
        assert client["service_open_method"] is None, (
            f"Expected None, got {client['service_open_method']!r} "
            f"for taxpayer_id={client.get('taxpayer_id')}"
        )


def test_build_progress_payload_empty_list() -> None:
    """Edge case: no taxpayers produces an empty clients list."""
    payload = _build_progress_payload([])  # type: ignore[arg-type]
    assert payload["clients"] == []
    assert payload["total_clients"] == 0


# ---------------------------------------------------------------------------
# Tests for _update_progress_state
# ---------------------------------------------------------------------------


def _make_payload(*taxpayer_ids: int) -> dict:
    return {
        "progress": {
            "clients": [
                {"taxpayer_id": tid, "service_open_method": None}
                for tid in taxpayer_ids
            ],
            "completed_clients": 0,
            "running_client_id": None,
        },
    }


def test_update_progress_state_writes_service_open_method_on_done() -> None:
    """status='done' with service_open_method='direct_url' must update the matching
    client only; the other client must remain None."""
    payload = _make_payload(1, 2)

    _update_progress_state(
        extraction_job_id=99,
        payload=payload,
        taxpayer_id=1,
        status="done",
        error=None,
        metrics={"total_coes_detectados": 0},
        service_open_method="direct_url",
    )

    clients = payload["progress"]["clients"]
    assert clients[0]["service_open_method"] == "direct_url"
    assert clients[1]["service_open_method"] is None


def test_update_progress_state_writes_service_open_method_search_box() -> None:
    """service_open_method='search_box' is also stored correctly."""
    payload = _make_payload(10)

    _update_progress_state(
        extraction_job_id=1,
        payload=payload,
        taxpayer_id=10,
        status="done",
        error=None,
        metrics=None,
        service_open_method="search_box",
    )

    assert payload["progress"]["clients"][0]["service_open_method"] == "search_box"


def test_update_progress_state_preserves_none_on_error_status() -> None:
    """status='error' with service_open_method=None (failed before service-open)
    must store None — not overwrite with a stale value."""
    payload = _make_payload(5)

    _update_progress_state(
        extraction_job_id=2,
        payload=payload,
        taxpayer_id=5,
        status="error",
        error="something went wrong",
        metrics=None,
        service_open_method=None,
    )

    assert payload["progress"]["clients"][0]["service_open_method"] is None


def test_update_progress_state_running_does_not_set_service_open_method() -> None:
    """status='running' must NOT touch service_open_method (it's only set on terminal
    statuses: done / partial / error)."""
    payload = _make_payload(3)
    # Pre-seed a value to prove it isn't overwritten by 'running'
    payload["progress"]["clients"][0]["service_open_method"] = "search_box"

    _update_progress_state(
        extraction_job_id=3,
        payload=payload,
        taxpayer_id=3,
        status="running",
        error=None,
        metrics=None,
        service_open_method=None,
    )

    # 'running' branch doesn't touch service_open_method — value stays as-is
    assert payload["progress"]["clients"][0]["service_open_method"] == "search_box"
