from __future__ import annotations

from datetime import datetime, timedelta

from app.extensions import db
from app.models import Taxpayer


def _create_taxpayer(
    *,
    cuit: str = "20111111111",
    empresa: str = "Empresa Test",
    activo: bool = True,
    scheduler_activo: bool = False,
    scheduler_dias_semana: str = "lun,mar,mie,jue,vie",
    scheduler_hora_local: str = "06:00",
    scheduler_ultimo_ok: datetime | None = None,
    scheduler_ultimo_error: str | None = None,
    scheduler_ultimo_error_en: datetime | None = None,
) -> Taxpayer:
    item = Taxpayer()
    item.cuit = cuit
    item.empresa = empresa
    item.cuit_representado = cuit
    item.clave_fiscal_encrypted = "test"
    item.playwright_enabled = True
    item.activo = activo
    item.scheduler_activo = scheduler_activo
    item.scheduler_dias_semana = scheduler_dias_semana
    item.scheduler_hora_local = scheduler_hora_local
    item.scheduler_ultimo_ok = scheduler_ultimo_ok
    item.scheduler_ultimo_error = scheduler_ultimo_error
    item.scheduler_ultimo_error_en = scheduler_ultimo_error_en
    db.session.add(item)
    db.session.commit()
    return item


# --- PATCH /api/taxpayers/<id>/scheduler ---------------------------------


def test_patch_scheduler_actualiza_activo(client, admin_headers):
    t = _create_taxpayer(cuit="20111111111", scheduler_activo=False)

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"activo": True},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["taxpayer_id"] == t.id
    assert body["activo"] is True

    db.session.refresh(t)
    assert t.scheduler_activo is True


def test_patch_scheduler_actualiza_dias_semana_se_guarda_como_csv(client, admin_headers):
    t = _create_taxpayer(cuit="20111111112")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"dias_semana": ["lun", "mie", "vie"]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["dias_semana"] == ["lun", "mie", "vie"]

    db.session.refresh(t)
    assert t.scheduler_dias_semana == "lun,mie,vie"


def test_patch_scheduler_actualiza_hora_local(client, admin_headers):
    t = _create_taxpayer(cuit="20111111113")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"hora_local": "07:30"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["hora_local"] == "07:30"

    db.session.refresh(t)
    assert t.scheduler_hora_local == "07:30"


def test_patch_scheduler_hora_local_mal_formada_422(client, admin_headers):
    t = _create_taxpayer(cuit="20111111114")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"hora_local": "25:00"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "hora_local_invalida"


def test_patch_scheduler_dias_semana_invalidos_422(client, admin_headers):
    t = _create_taxpayer(cuit="20111111115")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"dias_semana": ["lun", "xxx", "vie"]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "dias_semana_invalido"
    assert body["detalle"]["invalidos"] == ["xxx"]


def test_patch_scheduler_actualiza_dias_extraccion(client, admin_headers):
    t = _create_taxpayer(cuit="20111111120")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"dias_extraccion": 30},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["dias_extraccion"] == 30

    db.session.refresh(t)
    assert t.scheduler_dias_extraccion == 30


def test_patch_scheduler_dias_extraccion_menor_a_1_devuelve_422(client, admin_headers):
    t = _create_taxpayer(cuit="20111111121")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"dias_extraccion": 0},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "validacion_fallida"
    assert body["detalle"]["recibido"] == 0


def test_patch_scheduler_dias_extraccion_mayor_a_366_devuelve_422(client, admin_headers):
    t = _create_taxpayer(cuit="20111111122")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"dias_extraccion": 367},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "validacion_fallida"
    assert body["detalle"]["recibido"] == 367


def test_patch_scheduler_dias_extraccion_no_entero_devuelve_422(client, admin_headers):
    t = _create_taxpayer(cuit="20111111123")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"dias_extraccion": "abc"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "validacion_fallida"


def test_patch_scheduler_taxpayer_inexistente_404(client, admin_headers):
    response = client.patch(
        "/api/taxpayers/99999/scheduler",
        json={"activo": True},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "taxpayer_no_encontrado"


def test_patch_scheduler_sin_auth_401(client):
    t = _create_taxpayer(cuit="20111111116")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"activo": True},
    )

    assert response.status_code == 401


def test_patch_scheduler_sin_admin_403(client, auth_headers):
    t = _create_taxpayer(cuit="20111111117")

    response = client.patch(
        f"/api/taxpayers/{t.id}/scheduler",
        json={"activo": True},
        headers=auth_headers,
    )

    assert response.status_code == 403


# --- POST /api/scheduler/run-now/<id> -----------------------------------


def test_post_run_now_encola_job(client, admin_headers, monkeypatch):
    t = _create_taxpayer(
        cuit="20222222221", scheduler_activo=True, activo=True
    )

    captured: dict[str, object] = {}

    class DummyRqJob:
        id = "rq-job-fake"

    class DummyQueue:
        name = "default"

        def enqueue(self, func, **kwargs):
            captured["func"] = func
            captured["kwargs"] = kwargs
            return DummyRqJob()

    monkeypatch.setattr("app.api.scheduler.get_queue", lambda: DummyQueue())

    def dummy_job(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.workers.playwright_jobs.run_playwright_pipeline_job",
        dummy_job,
    )

    response = client.post(
        f"/api/scheduler/run-now/{t.id}",
        headers=admin_headers,
    )

    assert response.status_code == 202
    body = response.get_json()
    assert body["taxpayer_id"] == t.id
    assert body["estado"] == "encolado"
    assert isinstance(body["extraction_job_id"], int)

    assert "func" in captured, "queue.enqueue debió ser llamado"
    assert captured["kwargs"]["extraction_job_id"] == body["extraction_job_id"]

    # Issue #101: el payload persistido debe incluir los mismos campos
    # descriptivos que playwright_lpg_run (no solo {trigger, taxpayer_id}).
    from app.models.extraction_job import ExtractionJob
    from app.extensions import db

    job = db.session.get(ExtractionJob, body["extraction_job_id"])
    expected_keys = {
        "fecha_desde",
        "fecha_hasta",
        "taxpayer_ids",
        "timeout_ms",
        "type_delay_ms",
        "slow_mo_ms",
        "post_action_delay_ms",
        "login_max_retries",
        "humanize_delays",
        "retry_max_attempts",
        "retry_base_delay_ms",
        "headless",
        "queue_name",
        "rq_job_id",
    }
    assert expected_keys.issubset(set((job.payload or {}).keys()))
    assert job.payload["queue_name"] == "default"
    assert job.payload["rq_job_id"] == "rq-job-fake"


def test_post_run_now_taxpayer_inactivo_409(client, admin_headers):
    t = _create_taxpayer(cuit="20222222222", activo=False, scheduler_activo=True)

    response = client.post(
        f"/api/scheduler/run-now/{t.id}",
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "taxpayer_inactivo"


def test_post_run_now_scheduler_inactivo_409(client, admin_headers):
    t = _create_taxpayer(cuit="20222222223", activo=True, scheduler_activo=False)

    response = client.post(
        f"/api/scheduler/run-now/{t.id}",
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "scheduler_inactivo"


def test_post_run_now_taxpayer_inexistente_404(client, admin_headers):
    response = client.post(
        "/api/scheduler/run-now/99999",
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "taxpayer_no_encontrado"


# --- GET /api/scheduler/status ------------------------------------------


def test_get_status_devuelve_totales_correctos(client, admin_headers):
    now = datetime(2026, 5, 14, 6, 30, 0)
    _create_taxpayer(
        cuit="30000000001",
        activo=True,
        scheduler_activo=True,
        scheduler_ultimo_ok=now,
    )
    _create_taxpayer(
        cuit="30000000002",
        activo=True,
        scheduler_activo=True,
        scheduler_ultimo_ok=now - timedelta(hours=1),
    )
    _create_taxpayer(cuit="30000000003", activo=True, scheduler_activo=False)
    _create_taxpayer(cuit="30000000004", activo=False, scheduler_activo=True)

    response = client.get("/api/scheduler/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.get_json()
    # 3 activos (los con activo=True)
    assert body["taxpayers_total"] == 3
    # 2 con scheduler activo y taxpayer activo
    assert body["taxpayers_activos_en_scheduler"] == 2
    assert body["ultimo_scrape_global"] == now.isoformat()
    assert body["con_error_reciente"] == []


def test_get_status_incluye_con_error_reciente(client, admin_headers):
    err_en = datetime(2026, 5, 14, 6, 15, 0)
    _create_taxpayer(
        cuit="30000000005",
        empresa="Foo SRL",
        activo=True,
        scheduler_activo=True,
        scheduler_ultimo_error="ARCA timeout",
        scheduler_ultimo_error_en=err_en,
    )
    _create_taxpayer(
        cuit="30000000006",
        empresa="Bar SA",
        activo=True,
        scheduler_activo=True,
    )

    response = client.get("/api/scheduler/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["con_error_reciente"]) == 1
    item = body["con_error_reciente"][0]
    assert item["empresa"] == "Foo SRL"
    assert item["ultimo_scrape_error"] == "ARCA timeout"
    assert item["ultimo_scrape_error_en"] == err_en.isoformat()


# --- PATCH /api/scheduler/bulk ------------------------------------------


def test_bulk_update_aplica_los_4_campos_a_todos(client, admin_headers):
    t1 = _create_taxpayer(cuit="30000000010", empresa="Empresa A")
    t2 = _create_taxpayer(cuit="30000000011", empresa="Empresa B")
    t3 = _create_taxpayer(cuit="30000000012", empresa="Empresa C")

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id, t2.id, t3.id],
            "activo": True,
            "dias_semana": ["lun", "mie", "vie"],
            "hora_local": "07:30",
            "dias_extraccion": 30,
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 3
    assert len(body["actualizados"]) == 3

    for original in (t1, t2, t3):
        db.session.refresh(original)
        assert original.scheduler_activo is True
        assert original.scheduler_dias_semana == "lun,mie,vie"
        assert original.scheduler_hora_local == "07:30"
        assert original.scheduler_dias_extraccion == 30


def test_bulk_update_lista_vacia_devuelve_422(client, admin_headers):
    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [], "activo": True},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "taxpayer_ids_invalido"
    assert "al menos una empresa" in body["mensaje"]


def test_bulk_update_ids_inexistentes_devuelve_404(client, admin_headers):
    t1 = _create_taxpayer(cuit="30000000020")

    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [t1.id, 99998, 99999], "activo": True},
        headers=admin_headers,
    )

    assert response.status_code == 404
    body = response.get_json()
    assert body["error"] == "taxpayers_no_encontrados"
    assert set(body["detalle"]["faltantes"]) == {99998, 99999}


def test_bulk_update_hora_local_mal_formada_devuelve_422(client, admin_headers):
    t1 = _create_taxpayer(cuit="30000000030")

    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [t1.id], "hora_local": "25:99"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "hora_local_invalida"
    assert body["mensaje"] == "La hora debe tener formato HH:MM."


def test_bulk_update_dias_extraccion_fuera_de_rango_devuelve_422(
    client, admin_headers
):
    t1 = _create_taxpayer(cuit="30000000040")

    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [t1.id], "dias_extraccion": 0},
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "validacion_fallida"
    assert body["mensaje"] == "El período debe estar entre 1 y 366 días."


def test_bulk_update_sin_auth_401(client):
    t1 = _create_taxpayer(cuit="30000000050")

    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [t1.id], "activo": True},
    )

    assert response.status_code == 401


def test_bulk_update_sin_admin_403(client, auth_headers):
    t1 = _create_taxpayer(cuit="30000000060")

    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [t1.id], "activo": True},
        headers=auth_headers,
    )

    assert response.status_code == 403


# --- GET /api/scheduler/taxpayers/<id>/last-error-detail ----------------


def test_get_last_error_detail_sin_jobs_devuelve_payload_vacio(
    client, admin_headers
):
    t = _create_taxpayer(cuit="30000000070")

    response = client.get(
        f"/api/scheduler/taxpayers/{t.id}/last-error-detail",
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["taxpayer_id"] == t.id
    assert body["failure_phase"] is None
    assert body["failure_message_technical"] is None
    assert body["finished_at"] is None


def test_get_last_error_detail_devuelve_ultimo_failed_scheduler(
    client, admin_headers
):
    from app.models import ExtractionJob

    t = _create_taxpayer(cuit="30000000080")
    finished_old = datetime(2026, 5, 13, 6, 0, 0)
    finished_new = datetime(2026, 5, 14, 6, 0, 0)

    # Job antiguo failed con scheduler operation
    old_job = ExtractionJob()
    old_job.taxpayer_id = t.id
    old_job.operation = "scheduler_lpg_extract"
    old_job.status = "failed"
    old_job.failure_phase = "LOGIN_START"
    old_job.failure_message_technical = "AUTH_FAILED | old"
    old_job.finished_at = finished_old
    db.session.add(old_job)

    # Job más reciente failed con scheduler operation
    new_job = ExtractionJob()
    new_job.taxpayer_id = t.id
    new_job.operation = "scheduler_run_now"
    new_job.status = "failed"
    new_job.failure_phase = "SEARCH_SERVICE"
    new_job.failure_message_technical = "ARCA_SLOW_AFTER_DROPDOWN | new"
    new_job.finished_at = finished_new
    db.session.add(new_job)

    # Job NO scheduler (debe ignorarse)
    manual_job = ExtractionJob()
    manual_job.taxpayer_id = t.id
    manual_job.operation = "playwright_lpg_run"
    manual_job.status = "failed"
    manual_job.failure_phase = "LOGIN_START"
    manual_job.failure_message_technical = "should be ignored"
    manual_job.finished_at = finished_new + timedelta(minutes=10)
    db.session.add(manual_job)

    db.session.commit()

    response = client.get(
        f"/api/scheduler/taxpayers/{t.id}/last-error-detail",
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["taxpayer_id"] == t.id
    assert body["extraction_job_id"] == new_job.id
    assert body["failure_phase"] == "SEARCH_SERVICE"
    assert body["failure_message_technical"] == "ARCA_SLOW_AFTER_DROPDOWN | new"
    assert body["finished_at"] == finished_new.isoformat()


def test_get_last_error_detail_taxpayer_inexistente_404(client, admin_headers):
    response = client.get(
        "/api/scheduler/taxpayers/99999/last-error-detail",
        headers=admin_headers,
    )

    assert response.status_code == 404
    body = response.get_json()
    assert body["error"] == "taxpayer_no_encontrado"


def test_get_last_error_detail_sin_auth_401(client):
    t = _create_taxpayer(cuit="30000000090")

    response = client.get(
        f"/api/scheduler/taxpayers/{t.id}/last-error-detail",
    )

    assert response.status_code == 401


def test_get_last_error_detail_sin_admin_403(client, auth_headers):
    t = _create_taxpayer(cuit="30000000091")

    response = client.get(
        f"/api/scheduler/taxpayers/{t.id}/last-error-detail",
        headers=auth_headers,
    )

    assert response.status_code == 403
