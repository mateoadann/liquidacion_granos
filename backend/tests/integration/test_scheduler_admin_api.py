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

    class DummyQueue:
        name = "default"

        def enqueue(self, func, **kwargs):
            captured["func"] = func
            captured["kwargs"] = kwargs
            return object()

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


# --- PATCH /api/scheduler/bulk ------------------------------------------


def test_bulk_actualiza_multiples_taxpayers(client, admin_headers):
    t1 = _create_taxpayer(cuit="20444444441", scheduler_activo=False)
    t2 = _create_taxpayer(cuit="20444444442", scheduler_activo=False)
    t3 = _create_taxpayer(cuit="20444444443", scheduler_activo=False)

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id, t2.id, t3.id],
            "config": {
                "activo": True,
                "dias_semana": ["lun", "mie", "vie"],
                "hora_local": "07:30",
                "dias_extraccion": 45,
            },
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["actualizados"] == 3
    assert sorted(body["taxpayer_ids"]) == sorted([t1.id, t2.id, t3.id])
    assert body["config_aplicada"]["activo"] is True
    assert body["config_aplicada"]["dias_extraccion"] == 45

    for t in (t1, t2, t3):
        db.session.refresh(t)
        assert t.scheduler_activo is True
        assert t.scheduler_dias_semana == "lun,mie,vie"
        assert t.scheduler_hora_local == "07:30"
        assert t.scheduler_dias_extraccion == 45


def test_bulk_sin_taxpayer_ids_devuelve_422(client, admin_headers):
    response = client.patch(
        "/api/scheduler/bulk",
        json={"config": {"activo": True}},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.get_json()["error"] == "validacion_fallida"


def test_bulk_taxpayer_ids_vacio_devuelve_422(client, admin_headers):
    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [], "config": {"activo": True}},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.get_json()["error"] == "validacion_fallida"


def test_bulk_taxpayer_ids_no_lista_devuelve_422(client, admin_headers):
    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": "1,2,3", "config": {"activo": True}},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.get_json()["error"] == "validacion_fallida"


def test_bulk_config_vacio_devuelve_422(client, admin_headers):
    t1 = _create_taxpayer(cuit="20444444450")

    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [t1.id], "config": {}},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.get_json()["error"] == "validacion_fallida"


def test_bulk_id_inexistente_devuelve_404_con_detalle(client, admin_headers):
    t1 = _create_taxpayer(cuit="20444444451")

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id, 999_999],
            "config": {"activo": True},
        },
        headers=admin_headers,
    )

    assert response.status_code == 404
    body = response.get_json()
    assert body["error"] == "taxpayers_no_encontrados"
    assert body["detalle"]["faltan"] == [999_999]


def test_bulk_id_inexistente_NO_actualiza_los_demas(client, admin_headers):
    t1 = _create_taxpayer(cuit="20444444461", scheduler_activo=False)
    t2 = _create_taxpayer(cuit="20444444462", scheduler_activo=False)

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id, 999_999, t2.id],
            "config": {"activo": True},
        },
        headers=admin_headers,
    )

    assert response.status_code == 404
    # Atomicidad: ningún taxpayer válido debe haberse tocado.
    db.session.refresh(t1)
    db.session.refresh(t2)
    assert t1.scheduler_activo is False
    assert t2.scheduler_activo is False


def test_bulk_actualiza_solo_los_campos_provistos(client, admin_headers):
    t1 = _create_taxpayer(
        cuit="20444444471",
        scheduler_dias_semana="lun,mar,mie",
        scheduler_hora_local="06:00",
    )

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id],
            "config": {"dias_extraccion": 15},
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    db.session.refresh(t1)
    # dias_extraccion cambió, lo demás no.
    assert t1.scheduler_dias_extraccion == 15
    assert t1.scheduler_dias_semana == "lun,mar,mie"
    assert t1.scheduler_hora_local == "06:00"


def test_bulk_dias_extraccion_fuera_de_rango_devuelve_422(client, admin_headers):
    t1 = _create_taxpayer(cuit="20444444481")

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id],
            "config": {"dias_extraccion": 500},
        },
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.get_json()["error"] == "validacion_fallida"


def test_bulk_hora_local_mal_formada_devuelve_422(client, admin_headers):
    t1 = _create_taxpayer(cuit="20444444491")

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id],
            "config": {"hora_local": "26:99"},
        },
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.get_json()["error"] == "hora_local_invalida"


def test_bulk_dia_semana_invalido_devuelve_422(client, admin_headers):
    t1 = _create_taxpayer(cuit="20444444501")

    response = client.patch(
        "/api/scheduler/bulk",
        json={
            "taxpayer_ids": [t1.id],
            "config": {"dias_semana": ["lun", "xxx"]},
        },
        headers=admin_headers,
    )

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "dias_semana_invalido"
    assert body["detalle"]["invalidos"] == ["xxx"]


def test_bulk_sin_auth_devuelve_401(client):
    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [1], "config": {"activo": True}},
    )
    assert response.status_code == 401


def test_bulk_sin_admin_devuelve_403(client, auth_headers):
    response = client.patch(
        "/api/scheduler/bulk",
        json={"taxpayer_ids": [1], "config": {"activo": True}},
        headers=auth_headers,
    )
    assert response.status_code == 403


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
