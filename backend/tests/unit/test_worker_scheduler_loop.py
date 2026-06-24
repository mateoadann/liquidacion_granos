"""Tests para el loop de `worker_scheduler.main`.

Regresión: si un tick falla (ej: migración pendiente → UndefinedColumn), la
sesión SQLAlchemy queda con la transacción abortada. Como el app_context se
crea una sola vez fuera del while, sin rollback TODOS los ticks siguientes
fallan con InFailedSqlTransaction hasta reiniciar el contenedor. El loop debe
hacer db.session.rollback() en cada except.
"""
from __future__ import annotations

import pytest

import worker_scheduler


class _StopLoop(Exception):
    """Sale del while True tras la primera iteración."""


def test_tick_fallido_hace_rollback(app, monkeypatch):
    monkeypatch.setattr(worker_scheduler, "create_app", lambda: app)

    rollbacks: list[int] = []
    monkeypatch.setattr(
        worker_scheduler.db.session, "rollback", lambda: rollbacks.append(1)
    )

    def boom():
        raise RuntimeError("UndefinedColumn simulado")

    monkeypatch.setattr(worker_scheduler, "tick_scheduler", boom)
    monkeypatch.setattr(worker_scheduler, "reconcile_stale_jobs", lambda: 0)
    monkeypatch.setattr(worker_scheduler, "purge_old_screenshots", lambda *a: 0)
    # Corta el while True tras la primera iteración.
    monkeypatch.setattr(
        worker_scheduler.time, "sleep", lambda *_: (_ for _ in ()).throw(_StopLoop())
    )

    with pytest.raises(_StopLoop):
        worker_scheduler.main()

    # El tick falló → debió haber al menos un rollback.
    assert rollbacks, "el except del tick debe llamar db.session.rollback()"
