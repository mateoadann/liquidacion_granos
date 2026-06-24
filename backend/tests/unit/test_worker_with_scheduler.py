from __future__ import annotations

import worker as worker_mod


def test_worker_arranca_con_scheduler(monkeypatch):
    captured = {}

    class FakeWorker:
        def __init__(self, queues, connection):
            captured["queues"] = queues

        def work(self, with_scheduler=False):
            captured["with_scheduler"] = with_scheduler

    monkeypatch.setattr(worker_mod, "Worker", FakeWorker)
    monkeypatch.setattr(worker_mod, "Redis", type("R", (), {"from_url": staticmethod(lambda url: object())}))
    monkeypatch.setattr(worker_mod, "create_app", lambda: __import__("app").create_app())

    worker_mod.main()

    assert captured["with_scheduler"] is True
