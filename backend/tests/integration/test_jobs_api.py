from __future__ import annotations

from app.extensions import db
from app.models import Taxpayer, ExtractionJob


def _create_taxpayer(cuit: str = "20111111111", empresa: str = "Test SA") -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.activo = True
    db.session.add(item)
    db.session.commit()
    return item


def _create_jobs(taxpayer_id: int, count: int, *, status: str = "completed") -> None:
    for _ in range(count):
        job = ExtractionJob()
        job.taxpayer_id = taxpayer_id
        job.operation = "playwright_lpg_run"
        job.status = status
        job.payload = {}
        db.session.add(job)
    db.session.commit()


def test_jobs_list_paginated_returns_correct_shape(client, auth_headers):
    t = _create_taxpayer()
    _create_jobs(t.id, 25)

    response = client.get("/api/jobs?page=1&per_page=10", headers=auth_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert isinstance(body, dict)
    assert set(body.keys()) == {"jobs", "total", "page", "per_page", "pages"}
    assert body["total"] == 25
    assert body["page"] == 1
    assert body["per_page"] == 10
    assert body["pages"] == 3
    assert len(body["jobs"]) == 10


def test_jobs_list_paginated_page_2(client, auth_headers):
    t = _create_taxpayer()
    _create_jobs(t.id, 25)

    response = client.get("/api/jobs?page=2&per_page=10", headers=auth_headers)

    body = response.get_json()
    assert body["page"] == 2
    assert len(body["jobs"]) == 10


def test_jobs_list_paginated_last_page_partial(client, auth_headers):
    t = _create_taxpayer()
    _create_jobs(t.id, 25)

    response = client.get("/api/jobs?page=3&per_page=10", headers=auth_headers)

    body = response.get_json()
    assert body["page"] == 3
    assert len(body["jobs"]) == 5


def test_jobs_list_legacy_limit_returns_flat_array(client, auth_headers):
    """RecentJobsPanel uses ?limit=10 — must keep returning a flat array."""
    t = _create_taxpayer()
    _create_jobs(t.id, 25)

    response = client.get("/api/jobs?limit=10", headers=auth_headers)

    body = response.get_json()
    assert isinstance(body, list)
    assert len(body) == 10


def test_jobs_list_paginated_filters_by_status(client, auth_headers):
    t = _create_taxpayer()
    _create_jobs(t.id, 5, status="completed")
    _create_jobs(t.id, 3, status="failed")

    response = client.get(
        "/api/jobs?page=1&per_page=20&status=failed", headers=auth_headers
    )

    body = response.get_json()
    assert body["total"] == 3
    assert all(j["status"] == "failed" for j in body["jobs"])


def test_jobs_list_paginated_filters_by_taxpayer(client, auth_headers):
    t1 = _create_taxpayer(cuit="20111111111", empresa="T1")
    t2 = _create_taxpayer(cuit="20222222222", empresa="T2")
    _create_jobs(t1.id, 4)
    _create_jobs(t2.id, 2)

    response = client.get(
        f"/api/jobs?page=1&per_page=20&taxpayer_id={t2.id}", headers=auth_headers
    )

    body = response.get_json()
    assert body["total"] == 2
    assert all(j["taxpayer_id"] == t2.id for j in body["jobs"])


def test_jobs_list_paginated_per_page_capped_at_100(client, auth_headers):
    t = _create_taxpayer()
    _create_jobs(t.id, 5)

    response = client.get("/api/jobs?page=1&per_page=500", headers=auth_headers)

    body = response.get_json()
    assert body["per_page"] == 100
