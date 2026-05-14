# SPEC — Implementación v2 dentro de liquidacion_granos

**Proyecto:** `liquidacion_granos` (https://github.com/mateoadann/liquidacion_granos)
**Doc complementario:** [spec_api_liquidador_granos.md §16–§25](spec_api_liquidador_granos.md) (contrato API)
**Audiencia:** Agente/dev que va a implementar v2 del lado server, conectado al repo `liquidacion_granos`.
**Status:** pendiente implementación.

> Este SPEC vive en `rpa-holistor` porque fue donde se planeó. **Copiarlo al repo `liquidacion_granos`** (sugerido: `docs/spec_v2_implementacion.md`) cuando arranque la implementación.

---

## 1. Contexto y lo que ya existe

### Stack confirmado

- **Backend**: Flask 3 + SQLAlchemy 2 + Flask-Migrate (Alembic). Postgres 16. Redis + rq para workers async.
- **Scraping ARCA**: Playwright (web scraping en `lpg_playwright_pipeline.py`) + `arca_arg` (WS LPG SOAP en `integrations/arca/client.py`).
- **Frontend**: React 18 + Vite + TanStack Query + Zustand + Tailwind.
- **Auth interna**: JWT (`require_auth`). **Auth de integración con rpa-holistor**: API key + admin token (`require_api_key`, `require_admin_token`).

### Lo que YA está implementado (no tocar para v2)

| Componente | Path | Rol |
|---|---|---|
| Modelo `CoeEstado` | `backend/app/models/coe_estado.py` | Tracking estado COE. Schema completo, no requiere cambios. |
| Modelo `LpgDocument` | `backend/app/models/lpg_document.py` | Documento Arca + `datos_limpios` parseados. |
| Modelo `Taxpayer` | `backend/app/models/taxpayer.py` | "Empresa" (cliente del estudio). **v2 lo extiende** con columnas de scheduler. |
| Service `coe_estado_service.py` | `backend/app/services/` | CRUD + transiciones + `calcular_hash`. Reusable. |
| Service `json_v7_exporter.py` | `backend/app/services/` | **`build_json_v7(documents, taxpayer, mes, anio)` — pieza clave reusable en v2.** |
| Endpoints `/v1/*` | `backend/app/api/integration.py` (blueprint `integration_bp`) | `POST /v1/coes/cargado`, `GET /v1/coes/{coe}`, `GET /v1/coes/estados`, `POST /v1/coes/{coe}/forzar-sincronizado`. **Auditado: 19/19 OK contra rpa-holistor.** |
| Pipeline Playwright | `backend/app/services/lpg_playwright_pipeline.py` + worker `backend/app/workers/playwright_jobs.py` | Lo invoca el scheduler. |
| Endpoint actual export JSON v7 | `GET /api/clients/<id>/export/json-v7` (auth JWT) | **v2 lo reemplaza** por `GET /v2/liquidaciones` (auth API key) en `integration_bp`. La ruta vieja **se retira** junto con `CoeExportPanel.tsx`. |
| `CoeExportPanel.tsx` | `frontend/src/` | UI actual del Exportar. **Se retira en la misma iteración que entra el scheduler.** |

### Lo que falta (lo cubre este SPEC)

1. Extender `Taxpayer` con columnas de scheduler.
2. Endpoint nuevo `GET /v2/liquidaciones` con filtros temporales + empresa.
3. Endpoint nuevo `GET /v2/empresas` (lista + config scheduler).
4. Scheduler engine (cron-driven que invoca `lpg_playwright_pipeline`).
5. Panel admin frontend para configurar el scheduler por empresa.
6. Retirar `CoeExportPanel.tsx` y `GET /api/clients/<id>/export/json-v7`.

---

## 2. Decisiones de diseño

### 2.1 Config del scheduler: columnas en `Taxpayer` (no tabla separada)

El SPEC contractual menciona "tabla `empresas_scheduler`" como nombre genérico. Pero el modelo `Taxpayer` ya cumple el rol de "empresa" y tiene columnas equivalentes (`activo`, `playwright_enabled`). Agregar columnas es **más coherente** con el código actual.

Trade-off:
- ✅ Una sola fuente de verdad por empresa. JOIN gratis.
- ✅ Migración trivial (un solo `ALTER TABLE`).
- ❌ Si en el futuro hay multi-API-key con scopes por empresa o necesitamos varios scheduler-profiles por cliente, conviene migrar a tabla separada. Pero para v2 no aplica.

**Decisión: extender `Taxpayer`.**

### 2.2 Engine del scheduler: rq-scheduler

`liquidacion_granos` ya usa `rq` + Redis (`backend/app/queue.py`, `backend/worker.py`). Agregar `rq-scheduler` reutiliza la misma infra.

Alternativa descartada: APScheduler in-process. Funcionaría pero no escala si en algún momento hay múltiples workers, y reinventa lo que `rq-scheduler` resuelve.

**Decisión: `rq-scheduler` + worker dedicado `backend/worker_scheduler.py`.**

### 2.3 Reutilización de `json_v7_exporter`

`build_json_v7(documents, taxpayer, mes, anio)` ya hace el trabajo de armar el cuerpo v7.1. Solo hay que:
- Generalizarlo para que acepte **múltiples taxpayers** (no uno solo). Hoy asume un cliente; v2 trae todos. Refactor: nueva función `build_json_v7_bulk(docs_por_taxpayer, fecha_filtro)` que arma el sobre con `meta.total_liquidaciones` y un `liquidaciones[]` plano.
- El cuerpo del response es **idéntico al actual** salvo `meta.fuente="api_v2_liquidaciones"` y `meta.filtros_aplicados`.

### 2.4 Sin filtro server-side por estado

El contrato dice: el GET v2 devuelve **todos** los COEs que matchean el filtro temporal/empresa, sin importar el estado del lado server. Rpa-holistor decide qué hacer con cada uno según su ledger local.

Implicancia: la query subyacente filtra por fecha y empresa pero **NO** por `coe_estado.estado`. Devuelve también los `cargado` (rpa-holistor los ignora silenciosamente).

### 2.5 Side-effect cero en el GET

`GET /v2/liquidaciones` NO modifica el estado de ningún COE. La transición `descargado → cargado` la sigue disparando `POST /v1/coes/cargado` (sin cambios).

---

## 3. Cambios al modelo de datos

### Migración Alembic nueva

Crear `backend/migrations/versions/YYYYMMDD_NNNN_add_taxpayer_scheduler_columns.py`:

```python
from alembic import op
import sqlalchemy as sa

revision = "..."
down_revision = "20260513_0009"  # Ajustar al último

def upgrade():
    op.add_column("taxpayer", sa.Column("scheduler_activo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("taxpayer", sa.Column("scheduler_dias_semana", sa.String(50), nullable=False, server_default="lun,mar,mie,jue,vie"))
    op.add_column("taxpayer", sa.Column("scheduler_hora_local", sa.String(5), nullable=False, server_default="06:00"))
    op.add_column("taxpayer", sa.Column("scheduler_ultimo_ok", sa.DateTime(), nullable=True))
    op.add_column("taxpayer", sa.Column("scheduler_ultimo_error", sa.Text(), nullable=True))
    op.add_column("taxpayer", sa.Column("scheduler_ultimo_error_en", sa.DateTime(), nullable=True))
    op.create_index("idx_taxpayer_scheduler_activo", "taxpayer", ["scheduler_activo"])

def downgrade():
    op.drop_index("idx_taxpayer_scheduler_activo", table_name="taxpayer")
    op.drop_column("taxpayer", "scheduler_ultimo_error_en")
    op.drop_column("taxpayer", "scheduler_ultimo_error")
    op.drop_column("taxpayer", "scheduler_ultimo_ok")
    op.drop_column("taxpayer", "scheduler_hora_local")
    op.drop_column("taxpayer", "scheduler_dias_semana")
    op.drop_column("taxpayer", "scheduler_activo")
```

### Modelo `Taxpayer` actualizado

En `backend/app/models/taxpayer.py` agregar:

```python
scheduler_activo = db.Column(db.Boolean, nullable=False, default=False)
scheduler_dias_semana = db.Column(db.String(50), nullable=False, default="lun,mar,mie,jue,vie")
scheduler_hora_local = db.Column(db.String(5), nullable=False, default="06:00")
scheduler_ultimo_ok = db.Column(db.DateTime, nullable=True)
scheduler_ultimo_error = db.Column(db.Text, nullable=True)
scheduler_ultimo_error_en = db.Column(db.DateTime, nullable=True)
```

### Modelo `CoeEstado`

**Sin cambios.** v2 no agrega columnas. `hash_payload_arca`, `anulado_en` quedan para v3.

---

## 4. Backend: endpoints nuevos

Todos en `backend/app/api/integration.py` (blueprint `integration_bp` ya registrado bajo `/api`). Auth `X-API-Key` ya implementada vía `@require_api_key`.

### 4.1 `GET /api/v2/liquidaciones`

```python
@integration_bp.get("/v2/liquidaciones")
@require_api_key
def get_v2_liquidaciones():
    desde = request.args.get("desde_fecha_emision")    # ISO date
    hasta = request.args.get("hasta_fecha_emision")    # ISO date
    cuits = request.args.getlist("cuit_empresa")       # repetible

    # Validar formatos (devolver 422 si mal formado)
    # ...

    # Query: LpgDocument JOIN Taxpayer JOIN CoeEstado (outer)
    # Filtrar por:
    #   - Taxpayer.scheduler_activo = True
    #   - LpgDocument.taxpayer.cuit_representado IN cuits si cuits no vacío
    #   - extract_fecha_liquidacion(doc) BETWEEN desde Y hasta si especificados
    # NO filtrar por coe_estado.estado.

    docs = ...
    body = build_json_v7_bulk(
        docs=docs,
        filtros={"desde_fecha_emision": desde, "hasta_fecha_emision": hasta, "cuit_empresa": cuits or None},
    )
    return jsonify(body), 200
```

Refactor en `json_v7_exporter.py`: nueva función `build_json_v7_bulk(docs, filtros)`:

```python
def build_json_v7_bulk(docs: list[LpgDocument], filtros: dict) -> dict:
    liquidaciones = []
    for doc in docs:
        taxpayer = doc.taxpayer
        if not taxpayer:
            continue
        fecha_liq = extract_fecha_liquidacion(doc)  # ya existe
        if not fecha_liq:
            continue
        mes = int(fecha_liq.split("-")[1])
        anio = int(fecha_liq.split("-")[0])
        # estado_origen lo deriva del CoeEstado relacionado
        estado_origen = doc.coe_estado.estado if doc.coe_estado else "pendiente"
        id_liquidacion = doc.coe_estado.id_liquidacion if doc.coe_estado else None
        liquidaciones.append(transform_single(
            doc=doc, taxpayer=taxpayer, mes=mes, anio=anio,
            id_liquidacion=id_liquidacion, estado_origen=estado_origen,
        ))

    return {
        "schema_version": "v7.1",
        "meta": {
            "generado_en": now_cordoba_naive().isoformat(),
            "generador": "liquidacion-granos@2.0.0",
            "batch_id": f"b_{now_cordoba_naive().strftime('%Y%m%d_%H%M%S')}",
            "fuente": "api_v2_liquidaciones",
            "filtros_aplicados": filtros,
            "total_liquidaciones": len(liquidaciones),
        },
        "liquidaciones": liquidaciones,
    }
```

Errores: 401 (`api_key_invalida` ya cubierto por `@require_api_key`), 422 si fechas mal formadas, 503 si último scrape global > 24h (opcional, no bloquea respuesta).

### 4.2 `GET /api/v2/empresas`

```python
@integration_bp.get("/v2/empresas")
@require_api_key
def get_v2_empresas():
    taxpayers = Taxpayer.query.filter_by(activo=True).order_by(Taxpayer.empresa).all()
    ultimo_global = db.session.query(db.func.max(Taxpayer.scheduler_ultimo_ok)).scalar()
    return jsonify({
        "total": len(taxpayers),
        "ultimo_scrape_global": ultimo_global.isoformat() if ultimo_global else None,
        "empresas": [
            {
                "cuit_empresa": t.cuit_representado,
                "razon_social": t.empresa,
                "scheduler": {
                    "activo": t.scheduler_activo,
                    "dias_semana": t.scheduler_dias_semana.split(",") if t.scheduler_dias_semana else [],
                    "hora_local": t.scheduler_hora_local,
                    "ultimo_scrape_ok": t.scheduler_ultimo_ok.isoformat() if t.scheduler_ultimo_ok else None,
                    "ultimo_scrape_error": t.scheduler_ultimo_error,
                },
            }
            for t in taxpayers
        ],
    }), 200
```

### 4.3 Tests integration

`backend/tests/integration/test_v2_liquidaciones_api.py`:
- `test_get_sin_filtros_devuelve_todas_las_liquidaciones`
- `test_get_filtra_por_desde_fecha_emision`
- `test_get_filtra_por_hasta_fecha_emision`
- `test_get_filtra_por_cuit_empresa_repetible`
- `test_get_NO_modifica_estado_de_coe_estado`
- `test_get_devuelve_schema_v7_1_valido`
- `test_get_sin_api_key_devuelve_401`
- `test_get_fecha_mal_formada_devuelve_422`

`backend/tests/integration/test_v2_empresas_api.py`:
- `test_get_lista_solo_taxpayers_activos`
- `test_get_incluye_scheduler_config_completa`
- `test_get_ultimo_scrape_global_es_max_de_taxpayers`

---

## 5. Scheduler engine

### 5.1 Service nuevo: `backend/app/services/scheduler_service.py`

Responsabilidades:
- Iterar `Taxpayer.query.filter_by(scheduler_activo=True, activo=True).all()`.
- Para cada uno, decidir si "le toca correr ahora" según `scheduler_dias_semana` + `scheduler_hora_local` y la hora actual TZ Cordoba.
- Disparar `LpgPlaywrightPipelineService` (la misma que usa hoy `playwright_jobs.py`).
- Actualizar `scheduler_ultimo_ok` o `scheduler_ultimo_error` + `scheduler_ultimo_error_en` según resultado.

Función principal:

```python
def tick_scheduler() -> dict:
    """Se invoca cada N minutos. Decide qué empresas scrapear y dispara.

    Retorna resumen para logging.
    """
    now = now_cordoba_naive()
    dia = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"][now.weekday()]
    hora = now.strftime("%H:%M")

    taxpayers = Taxpayer.query.filter_by(
        scheduler_activo=True, activo=True
    ).all()

    disparados = []
    for t in taxpayers:
        dias = (t.scheduler_dias_semana or "").split(",")
        if dia not in dias:
            continue
        if t.scheduler_hora_local != hora:
            # Asume tick cada minuto. Si el tick es cada N min, ajustar el match.
            continue
        # Idempotencia: si scheduler_ultimo_ok es de hace < 1h, skip
        if t.scheduler_ultimo_ok and (now - t.scheduler_ultimo_ok).total_seconds() < 3600:
            continue
        _disparar_extraccion(t)
        disparados.append(t.id)

    return {"disparados": disparados, "evaluados": len(taxpayers)}


def _disparar_extraccion(taxpayer: Taxpayer) -> None:
    """Crea un ExtractionJob + encola en rq el worker playwright."""
    job = ExtractionJob(
        taxpayer_id=taxpayer.id,
        operation="scheduler_lpg_extract",
        status="pending",
    )
    db.session.add(job)
    db.session.commit()
    # Enqueue
    from app.queue import enqueue_playwright_job
    enqueue_playwright_job(job.id)
```

### 5.2 Hook al worker existente

`backend/app/workers/playwright_jobs.py` ya recibe `ExtractionJob`. **Modificar al final del worker**: si `job.operation == "scheduler_lpg_extract"`, al terminar exitoso actualizar `taxpayer.scheduler_ultimo_ok = now()`. Si falla, `scheduler_ultimo_error` + `scheduler_ultimo_error_en`.

### 5.3 Worker dedicado: `backend/worker_scheduler.py`

```python
"""Worker que corre tick_scheduler() periódicamente."""
import time
import logging
from app import create_app
from app.services.scheduler_service import tick_scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

INTERVAL_SECONDS = 60  # 1 tick por minuto

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        log.info("scheduler_worker arrancado, tick cada %ds", INTERVAL_SECONDS)
        while True:
            try:
                resumen = tick_scheduler()
                if resumen["disparados"]:
                    log.info("tick: %s", resumen)
            except Exception:
                log.exception("scheduler tick falló")
            time.sleep(INTERVAL_SECONDS)
```

### 5.4 Docker compose

Agregar servicio en `docker-compose.yml`:

```yaml
scheduler_worker:
  build:
    context: ./backend
    dockerfile: Dockerfile
  command: python -u worker_scheduler.py
  depends_on:
    - backend
    - redis
    - postgres
  env_file:
    - .env
  restart: unless-stopped
```

### 5.5 Tests scheduler

`backend/tests/unit/test_scheduler_service.py`:
- `test_tick_ignora_taxpayers_inactivos`
- `test_tick_ignora_scheduler_activo_false`
- `test_tick_respeta_dia_semana`
- `test_tick_respeta_hora_local`
- `test_tick_no_dispara_si_ultimo_ok_reciente`
- `test_disparar_extraccion_crea_extraction_job_y_encola`
- `test_worker_persiste_scheduler_ultimo_ok_en_caso_de_exito`
- `test_worker_persiste_scheduler_ultimo_error_en_caso_de_fallo`

---

## 6. Frontend

### 6.1 Retirar

- `frontend/src/CoeExportPanel.tsx` (eliminar archivo).
- La ruta que lo navega (probablemente en `App.tsx` o un router).
- El cliente API correspondiente (`frontend/src/api/coes.ts` o donde esté `downloadJsonV7`).
- Endpoint backend `GET /api/clients/<id>/export/json-v7` (eliminar de `clients.py` o donde viva).
- Tests obsoletos: `backend/tests/integration/test_json_v7_endpoint.py`, `test_export_rpa.py` — revisar qué partes siguen aplicando para v2 y migrar.

### 6.2 Agregar — Panel admin "Scheduler"

Nuevo componente `frontend/src/components/dashboard/SchedulerPanel.tsx` (o página dedicada bajo `/scheduler`):

Funcionalidades:
- Lista de Taxpayers con columnas: empresa, CUIT, `scheduler_activo` (toggle), `dias_semana` (multi-select), `hora_local` (time picker), `ultimo_scrape_ok`, `ultimo_scrape_error` (badge rojo si != null).
- Click "Editar" abre modal con dias_semana + hora_local.
- Botón "Scrapear ahora" por fila — endpoint nuevo `POST /api/scheduler/run-now/{taxpayer_id}` (auth JWT) que invoca `_disparar_extraccion` directamente, sin esperar al tick.

Endpoints backend complementarios para esta UI (en blueprint nuevo `scheduler_bp` o agregados a `taxpayers_bp`):

- `PATCH /api/taxpayers/{id}/scheduler` — body `{activo, dias_semana, hora_local}`. Auth JWT + admin.
- `POST /api/scheduler/run-now/{taxpayer_id}` — dispara extracción ad-hoc. Auth JWT + admin.
- `GET /api/scheduler/status` — vista resumen (cuántos activos, último tick, próximas ejecuciones).

### 6.3 Tests frontend

- Component test del panel (cambia toggle → llama API).
- E2E happy path (Playwright o Cypress si ya hay setup) — opcional.

---

## 7. Plan de implementación (orden sugerido)

### Backend (~10h)

1. **Migración Alembic** (1h) — columnas en `taxpayer` + modelo actualizado.
2. **Refactor `json_v7_exporter.build_json_v7_bulk`** (1h) — nueva función para múltiples taxpayers.
3. **`GET /api/v2/liquidaciones`** (2h) — endpoint + query con filtros + reusa exporter.
4. **`GET /api/v2/empresas`** (1h).
5. **`scheduler_service.tick_scheduler()`** + tests unit (2h).
6. **Worker dedicado `worker_scheduler.py` + entry docker-compose** (1h).
7. **Endpoints admin para UI** (`PATCH /taxpayers/{id}/scheduler`, `POST /scheduler/run-now`, `GET /scheduler/status`) (1.5h).
8. **Tests integration v2** (1.5h).

### Frontend (~5h)

9. **`SchedulerPanel.tsx`** (3h) — tabla + edit modal + toggle.
10. **Retirar `CoeExportPanel.tsx`** + rutas (0.5h).
11. **API client + types TS** (1h).
12. **Tests** (0.5h).

### Retirada del flujo viejo (~1h)

13. Eliminar endpoint `GET /api/clients/<id>/export/json-v7` y migrar/eliminar tests obsoletos.

### Integración end-to-end con rpa-holistor (~2h)

14. Levantar liquidacion_granos con scheduler activo en una empresa de test.
15. Disparar "Scrapear ahora" → confirmar que aparecen COEs en `coe_estado`.
16. Desde rpa-holistor, hacer `GET /v2/liquidaciones?desde_fecha_emision=...` → confirmar respuesta v7.1.
17. Validar criterios de aceptación §22 del SPEC contractual.

**Total estimado: ~18h** (más holgado que el spec contractual original que decía 14h, porque incluye frontend + retirada del flujo viejo).

---

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El tick del scheduler corre cada minuto pero el match `scheduler_hora_local == "HH:MM"` puede skippear ejecuciones si el tick se desincroniza (ej. cae a 06:00:59 y el match es a 06:01) | Cambiar match a "hora_local ≤ ahora ≤ hora_local + 5min" + flag `scheduler_ultimo_ok` para no doble-disparar. |
| `LpgPlaywrightPipelineService` puede tardar minutos por taxpayer; si el scheduler dispara 414 a las 06:00, satura | El worker rq procesa los jobs uno a uno (queue serial). Tolerable para 414 empresas si el scrape promedio es < 1 min. Si no, agregar prioridad o ventana de horario. |
| El frontend del "Scheduler" depende de auth JWT; necesita rol admin que no sé si existe ya | Verificar `middleware/auth_middleware.py` y rol disponible. Si no hay, definir uno (`require_admin`). |
| El refactor de `json_v7_exporter` puede romper el endpoint viejo si todavía está vivo durante migración | Mantener `build_json_v7` antiguo en paralelo a `build_json_v7_bulk`. Retirar solo cuando frontend nuevo esté activo. |
| Volumen del GET v2: 450 liq/mes × ventana 6 meses ≈ 5-15 MB JSON por request | Tolerable. Si crece a > 50 MB, agregar paginación `?limit=N&offset=M` simple. No requiere cursor en v2. |
| `taxpayer.cuit_representado` puede estar vacío en taxpayers viejos | Filtrar fuera del GET v2: `WHERE cuit_representado != ''`. Loggear los que se omiten. |
| El scheduler arranca con `scheduler_activo=False` por defecto en la migración → 0 empresas operando | Por diseño. El operador activa una por una desde la UI nueva. Documentar en el README. |

---

## 9. Lo que NO se implementa (queda para v3 o más adelante)

| Feature | Razón |
|---|---|
| Tabla `coes_eventos` + cursor opaco + `GET /v2/coes/nuevos` con eventos | El bulk GET con filtro temporal alcanza para 450 liq/mes. Cursor justifica complejidad solo si el volumen crece. |
| Estado `anulado_arca` server-side + detector de anulación con N scrapes | Anulación es caso raro y manejable manualmente. Detector con tolerancia es código no trivial. |
| `GET /v2/coes/{coe}` extendido con historial de transiciones | `GET /v1/coes/{coe}` cubre el caso. Historial detallado solo si hay dashboard que lo aproveche. |
| API key con scope por empresa | rpa-holistor es instalación única hoy. Si en el futuro hay multi-tenant, agregar columna `api_keys.cuits_autorizados` y filtrar en `@require_api_key`. |
| F15 "anular asiento en Holistor" automático | Decisión contable. Hoy queda como flag manual en rpa-holistor. |

---

## 10. Cross-references

- **Contrato API**: [spec_api_liquidador_granos.md](spec_api_liquidador_granos.md) §16–§25.
- **Ledger rpa-holistor**: [spec_ledger_rpa_holistor.md](spec_ledger_rpa_holistor.md).
- **Flujo end-to-end**: SPEC contractual §16 y §20.

---

## 11. Checklist final antes de merge a `main`

- [ ] Migración Alembic corre limpio en ambiente local y en CI.
- [ ] `GET /v2/liquidaciones` y `GET /v2/empresas` documentados en README + OpenAPI si lo usan.
- [ ] Tests unit + integration verdes (>90% cobertura del código nuevo).
- [ ] `worker_scheduler` arranca en docker-compose y un tick de prueba dispara una extracción.
- [ ] Panel admin frontend operativo (activar empresa, ver `ultimo_scrape_ok`).
- [ ] `CoeExportPanel.tsx` retirado del bundle.
- [ ] `GET /api/clients/<id>/export/json-v7` retornando 404 / 410 Gone.
- [ ] rpa-holistor `POST /v1/coes/cargado` sigue funcionando contra v2 server (no rompimos v1).
- [ ] CHANGELOG actualizado.
