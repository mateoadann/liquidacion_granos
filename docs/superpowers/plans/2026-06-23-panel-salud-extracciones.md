# Panel de salud de extracciones — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar al usuario una vista de solo lectura que muestre, por cliente activo, hace cuántos días no se extrae con éxito y cuál es la causa accionable, clasificada con un semáforo.

**Architecture:** Endpoint de agregación read-only (`GET /api/extracciones/salud`) que lee `extraction_job` y clasifica cada cliente en verde/amarillo/rojo/gris. Una columna nueva `failure_code` en `extraction_job` da el clasificador estable. El frontend consume el endpoint con TanStack Query y lo muestra en una página nueva. No se toca el pipeline de Playwright ni el scheduler salvo para persistir el código de fallo.

**Tech Stack:** Flask + SQLAlchemy + Alembic (backend), pytest, React 18 + TypeScript + TanStack Query + Tailwind (frontend).

## Global Constraints

- Timestamps en timezone America/Argentina/Cordoba (usar `now_cordoba_naive()` de `app/time_utils.py`).
- Errores de API: `{"error": "..."}` con status apropiado.
- Endpoints protegidos con `@require_auth` (de `app.middleware`).
- Blueprints decorados con `@bp.get`/`@bp.post`; registrados en `app/api/__init__.py` con `url_prefix="/api"`.
- `from __future__ import annotations` en módulos tipados nuevos.
- Payloads backend en `snake_case`; modelos frontend en `camelCase`; adapters centralizados.
- TypeScript estricto — no debilitar tipos. 2-space indent, double quotes, semicolons.
- Logical delete: contribuyentes con `activo = False` se excluyen.
- Mensajes al usuario: usar "Arca" (no "ARCA"/"AFIP"); nunca mencionar "playwright"/"scheduler"/"scrape"/"worker".
- Códigos de fallo conocidos del mapper: `AUTH_FAILED`, `SERVICE_NOT_ADHERED`, `EMPRESA_NOT_FOUND`, `TRANSIENT_LOGIN`, `ARCA_SLOW_AFTER_DROPDOWN`, `OPEN_SERVICE_TIMEOUT`, `CONSULTA_FAILURE`, `NETWORK_ERROR`, `WS_COE_ERRORS`, `UNKNOWN_ERROR`.
- Códigos ROJO (accionable): `AUTH_FAILED`, `SERVICE_NOT_ADHERED`, `EMPRESA_NOT_FOUND`. El resto es transitorio (amarillo, sube a rojo con `dias_sin_exito >= 3`).
- Comandos de test: backend `cd backend && python3 -m pytest <ruta> -q`; frontend `cd frontend && npx tsc --noEmit` y `npm run build`. (En este entorno el binario es `python3`, no `python`.)

---

## File Structure

| Archivo | Responsabilidad |
|---------|-----------------|
| `backend/app/services/extraction_failure_mapper.py` | `map_failure` devuelve `(user_es, tech_en, code)` |
| `backend/migrations/versions/20260623_0015_*.py` | Migración: columna `failure_code` |
| `backend/app/models/extraction_job.py` | Campo `failure_code` |
| `backend/app/workers/playwright_jobs.py` | Persistir `failure_code` al fallar |
| `backend/app/services/scheduler_service.py` | Setear `failure_code` en jobs stale |
| `backend/app/services/extraction_health.py` | **NUEVO** — lógica de clasificación de salud por cliente |
| `backend/app/api/extracciones.py` | **NUEVO** — blueprint con `GET /salud` |
| `backend/app/api/__init__.py` | Registrar el blueprint nuevo |
| `backend/tests/unit/test_extraction_failure_mapper.py` | Actualizar a tupla de 3 |
| `backend/tests/unit/test_extraction_health.py` | **NUEVO** — tests de clasificación |
| `frontend/src/api/extracciones.ts` | **NUEVO** — cliente HTTP + tipos |
| `frontend/src/hooks/useExtractionHealth.ts` | **NUEVO** — hook TanStack Query |
| `frontend/src/pages/ExtractionHealthPage.tsx` | **NUEVO** — página + tabla + cards |
| navegación (router/menú existente) | Agregar ruta a la página nueva |

La clasificación vive en un servicio (`extraction_health.py`) separado del endpoint para poder testearla con datos en DB sin pasar por HTTP, y para que el futuro reporte diario (feature 078) la reuse.

---

## Task 1: `map_failure` devuelve el código de fallo

**Files:**
- Modify: `backend/app/services/extraction_failure_mapper.py`
- Test: `backend/tests/unit/test_extraction_failure_mapper.py`

**Interfaces:**
- Produces: `map_failure(phase, error_type, dropdown_clicked=False) -> tuple[str, str, str]` — ahora `(mensaje_usuario, mensaje_técnico, código)`. El código es uno de los listados en Global Constraints, o `"UNKNOWN_ERROR"` por defecto.

- [ ] **Step 1: Leer el estado actual del test y del mapper**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_failure_mapper.py -q`
Expected: PASS (los tests actuales esperan tupla de 2). Esto confirma el punto de partida.

- [ ] **Step 2: Escribir el test que falla (espera código como 3er valor)**

En `backend/tests/unit/test_extraction_failure_mapper.py`, agregar:

```python
from app.services.extraction_failure_mapper import map_failure
from app.services.extraction_phases import ExtractionPhase


def test_map_failure_returns_code_auth_failed():
    user, tech, code = map_failure(ExtractionPhase.LOGIN_START, "auth_failed")
    assert code == "AUTH_FAILED"
    assert "clave fiscal" in user.lower()


def test_map_failure_returns_code_service_not_adhered():
    user, tech, code = map_failure(ExtractionPhase.SEARCH_SERVICE, "timeout", dropdown_clicked=False)
    assert code == "SERVICE_NOT_ADHERED"


def test_map_failure_returns_code_empresa_not_found():
    user, tech, code = map_failure(ExtractionPhase.SELECT_EMPRESA, "unknown")
    assert code == "EMPRESA_NOT_FOUND"


def test_map_failure_returns_code_network():
    user, tech, code = map_failure(None, "network")
    assert code == "NETWORK_ERROR"


def test_map_failure_returns_code_unknown_default():
    user, tech, code = map_failure(None, "unknown")
    assert code == "UNKNOWN_ERROR"
```

- [ ] **Step 3: Correr el test para verificar que falla**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_failure_mapper.py -k "returns_code" -q`
Expected: FAIL — `ValueError: not enough values to unpack (expected 3, got 2)`.

- [ ] **Step 4: Modificar `map_failure` para devolver el código**

En `backend/app/services/extraction_failure_mapper.py`, cambiar la firma y cada `return` para incluir el código como 3er elemento. El código ya está embebido al inicio del 2º valor actual; extraerlo a una constante explícita. Reemplazar el cuerpo de `map_failure` por:

```python
def map_failure(
    phase: ExtractionPhase | None,
    error_type: str,
    dropdown_clicked: bool = False,
) -> tuple[str, str, str]:
    if phase in _LOGIN_PHASES:
        if error_type == "auth_failed":
            return (_AUTH_FAILED_USER_ES, "AUTH_FAILED at login", "AUTH_FAILED")
        if error_type in _TRANSIENT_ERRORS:
            return (_TRANSIENT_LOGIN_USER_ES, "TRANSIENT_LOGIN", "TRANSIENT_LOGIN")

    if phase == ExtractionPhase.SEARCH_SERVICE:
        if dropdown_clicked and error_type in _SEARCH_SERVICE_AFTER_DROPDOWN_ERRORS:
            return (
                _ARCA_SLOW_AFTER_DROPDOWN_USER_ES,
                "ARCA_SLOW_AFTER_DROPDOWN",
                "ARCA_SLOW_AFTER_DROPDOWN",
            )
        if not dropdown_clicked and error_type in _SERVICE_NOT_ADHERED_ERRORS:
            return (_SERVICE_NOT_ADHERED_USER_ES, "SERVICE_NOT_ADHERED", "SERVICE_NOT_ADHERED")

    if phase == ExtractionPhase.OPEN_SERVICE:
        return (_OPEN_SERVICE_TIMEOUT_USER_ES, "OPEN_SERVICE_TIMEOUT", "OPEN_SERVICE_TIMEOUT")

    if phase == ExtractionPhase.SELECT_EMPRESA:
        return (_EMPRESA_NOT_FOUND_USER_ES, "EMPRESA_NOT_FOUND", "EMPRESA_NOT_FOUND")

    if phase in _CONSULTA_PHASES:
        return (_CONSULTA_FAILURE_USER_ES, "CONSULTA_FAILURE", "CONSULTA_FAILURE")

    if phase in _WS_PHASES:
        return (_WS_COE_ERRORS_USER_ES, "WS_COE_ERRORS", "WS_COE_ERRORS")

    if error_type == "network":
        return (_NETWORK_ERROR_USER_ES, "NETWORK_ERROR", "NETWORK_ERROR")

    return (_UNKNOWN_ERROR_USER_ES, "UNKNOWN_ERROR", "UNKNOWN_ERROR")
```

> **IMPORTANTE:** antes de escribir esto, leer el cuerpo actual completo de `map_failure` (desde `def map_failure` hasta el `return` final) y preservar EXACTAMENTE las mismas ramas/condiciones que ya existen — arriba está el patrón, pero las constantes de mensaje (`_OPEN_SERVICE_TIMEOUT_USER_ES`, etc.) y el orden de ramas deben coincidir con el archivo real. Solo se agrega el 3er valor de la tupla; no cambiar la lógica de matching.

- [ ] **Step 5: Correr los tests del mapper**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_failure_mapper.py -q`
Expected: FAIL en los tests viejos que esperaban tupla de 2 (los actualizamos en el paso siguiente), PASS en los `returns_code`.

- [ ] **Step 6: Actualizar los tests viejos a desempaquetar 3 valores**

En el mismo archivo, buscar cada llamada `user, tech = map_failure(...)` y cambiarla a `user, tech, code = map_failure(...)`. No cambiar las aserciones existentes sobre `user`/`tech`.

- [ ] **Step 7: Correr todo el archivo de tests del mapper**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_failure_mapper.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/extraction_failure_mapper.py backend/tests/unit/test_extraction_failure_mapper.py
git commit -m "feat(extracciones): map_failure devuelve código de fallo estable"
```

---

## Task 2: Columna `failure_code` en `extraction_job`

**Files:**
- Modify: `backend/app/models/extraction_job.py`
- Create: `backend/migrations/versions/20260623_0015_add_failure_code.py`

**Interfaces:**
- Produces: `ExtractionJob.failure_code: str | None` — columna `VARCHAR(40)` nullable.

- [ ] **Step 1: Agregar el campo al modelo**

En `backend/app/models/extraction_job.py`, después de `failure_error_type = db.Column(db.String(64), nullable=True)`, agregar:

```python
    failure_code = db.Column(db.String(40), nullable=True)
```

- [ ] **Step 2: Crear la migración**

Crear `backend/migrations/versions/20260623_0015_add_failure_code.py`:

```python
"""Add failure_code column to extraction_job.

map_failure now returns a stable code (AUTH_FAILED, SERVICE_NOT_ADHERED, etc.)
used by the extraction-health panel to classify clients into a traffic-light
state. Persisting the code as its own column avoids parsing the technical
message string. Old jobs have NULL and are shown as "unknown/grey".

Revision ID: 20260623_0015
Revises: 20260527_0014
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "20260623_0015"
down_revision = "20260527_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "extraction_job",
        sa.Column("failure_code", sa.String(length=40), nullable=True),
    )


def downgrade():
    op.drop_column("extraction_job", "failure_code")
```

> Antes de fijar `down_revision`, confirmar el head actual con:
> `cd backend && python3 -c "import glob,re; [print(re.search(r'revision\s*=\s*[\"\x27]([^\"\x27]+)', open(f).read()).group(1)) for f in glob.glob('migrations/versions/*.py')]" | sort | tail`
> El head esperado es `20260527_0014`. Si no coincide, ajustar `down_revision`.

- [ ] **Step 3: Aplicar la migración localmente**

Run: `make db-upgrade`
Expected: aplica `20260623_0015` sin error. (Si se corre en Docker, el backend la aplica al arrancar.)

- [ ] **Step 4: Verificar la columna en la DB**

Run: `docker exec liquidacion_granos-postgres-1 psql -U liquidacion -d liquidacion_granos -c "\d extraction_job" | grep failure_code`
Expected: muestra `failure_code | character varying(40)`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/extraction_job.py backend/migrations/versions/20260623_0015_add_failure_code.py
git commit -m "feat(extracciones): columna failure_code en extraction_job"
```

---

## Task 3: Persistir `failure_code` en el worker y en jobs stale

**Files:**
- Modify: `backend/app/workers/playwright_jobs.py`
- Modify: `backend/app/services/scheduler_service.py`

**Interfaces:**
- Consumes: `map_failure(...) -> (user, tech, code)` (Task 1), `ExtractionJob.failure_code` (Task 2).
- Produces: jobs `failed`/`partial` nuevos tienen `failure_code` poblado.

> Contexto: `_update_job(...)` es un helper de `playwright_jobs.py` que hace `setattr` de los kwargs sobre el `ExtractionJob` y commitea. `_apply_taxpayer_failure(...)` (alrededor de la línea 160) llama `map_failure` y devuelve `(user_es, tech_combined)`. Hay tres puntos de persistencia de fallo: el callback por-taxpayer (~línea 442), la finalización del job (~línea 520) y el handler de excepción general (~línea 572). Leer esas regiones antes de editar; los números de línea son aproximados.

- [ ] **Step 1: Escribir el test de integración del worker (falla)**

Crear/append en `backend/tests/unit/test_playwright_jobs_failure_code.py`:

```python
from app.services.extraction_failure_mapper import map_failure
from app.services.extraction_phases import ExtractionPhase


def test_map_failure_tuple_is_three():
    # Guardrail: el worker depende de desempaquetar 3 valores.
    result = map_failure(ExtractionPhase.LOGIN_START, "auth_failed")
    assert len(result) == 3
```

Este test fija el contrato que el worker consume. (La cobertura end-to-end del worker la da `test_extraction_health.py` con datos en DB.)

- [ ] **Step 2: Correr el test**

Run: `cd backend && python3 -m pytest tests/unit/test_playwright_jobs_failure_code.py -q`
Expected: PASS (Task 1 ya lo garantiza). Sirve de guardrail.

- [ ] **Step 3: Actualizar `_apply_taxpayer_failure` para devolver y propagar el código**

En `playwright_jobs.py`, en la función `_apply_taxpayer_failure` (~línea 160), cambiar:
- la línea `user_es, tech_en = map_failure(phase, error_type, dropdown_clicked)` por `user_es, tech_en, code = map_failure(phase, error_type, dropdown_clicked)`
- agregar `client["failure_code"] = code` junto a las otras asignaciones del dict `client`
- cambiar el `return user_es, tech_combined` por `return user_es, tech_combined, code`
- actualizar la anotación de retorno a `-> tuple[str, str, str]`

- [ ] **Step 4: Actualizar los call sites de `_apply_taxpayer_failure`**

Buscar las llamadas (`grep -n "_apply_taxpayer_failure" backend/app/workers/playwright_jobs.py`). En el callback por-taxpayer (~línea 425), cambiar:
- `user_es, tech_combined = _apply_taxpayer_failure(...)` por `user_es, tech_combined, code = _apply_taxpayer_failure(...)`
- guardar `last_taxpayer_failure["code"] = code`
- agregar `failure_code=code` al `_update_job(...)` de ese bloque (~línea 438)

En la inicialización de `last_taxpayer_failure` (buscar dónde se crea el dict con `"phase"`, `"user_es"`, `"tech"`, `"error_type"`), agregar `"code": None`.

- [ ] **Step 5: Actualizar la finalización del job (failed/partial)**

En el bloque ~línea 490-520, donde se asignan `job_failure_user/tech/phase/error_type`, agregar:
```python
                    job_failure_code = last_taxpayer_failure["code"]
```
en ambas ramas (`failed` y `partial`), e inicializar `job_failure_code = None` junto a las otras `job_failure_*` por defecto (buscar dónde se declaran `job_failure_user = None`, etc.). Luego en el `_update_job(...)` de finalización (~línea 513) agregar `failure_code=job_failure_code`.

- [ ] **Step 6: Actualizar el handler de excepción general**

En el `except Exception as exc:` (~línea 568), cambiar `user_es, tech_en = map_failure(None, "unknown", False)` por `user_es, tech_en, code = map_failure(None, "unknown", False)` y agregar `failure_code=code` al `_update_job(...)` de ese bloque.

- [ ] **Step 7: Setear `failure_code` en jobs stale (scheduler_service)**

En `backend/app/services/scheduler_service.py`, donde se setea `job.failure_error_type = "stale_timeout"` (~línea 159), agregar:
```python
            job.failure_code = "UNKNOWN_ERROR"
```
(stale no es accionable → caerá en transitorio/gris, lo cual es correcto: no requiere que el usuario cambie nada.)

- [ ] **Step 8: Verificar compilación**

Run: `cd backend && python3 -m compileall app -q && echo OK`
Expected: `OK` sin errores.

- [ ] **Step 9: Correr la suite de workers/scheduler existente para no romper nada**

Run: `cd backend && python3 -m pytest tests/unit/test_playwright_early_step_robustness.py tests/unit/test_scheduler_defaults.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/workers/playwright_jobs.py backend/app/services/scheduler_service.py backend/tests/unit/test_playwright_jobs_failure_code.py
git commit -m "feat(extracciones): persistir failure_code al fallar un job"
```

---

## Task 4: Servicio de clasificación de salud

**Files:**
- Create: `backend/app/services/extraction_health.py`
- Test: `backend/tests/unit/test_extraction_health.py`

**Interfaces:**
- Consumes: `ExtractionJob.failure_code` (Task 2), `Taxpayer`, `now_cordoba_naive`.
- Produces:
  - `ACTIONABLE_CODES: set[str]` = `{"AUTH_FAILED", "SERVICE_NOT_ADHERED", "EMPRESA_NOT_FOUND"}`
  - `RED_THRESHOLD_DAYS: int` = `3`
  - `compute_health() -> dict` con forma:
    ```python
    {
      "generado_en": str,           # ISO, Cordoba
      "resumen": {"verde": int, "amarillo": int, "rojo": int, "gris": int},
      "clientes": list[dict],       # ver ClienteSalud abajo, ordenado rojo>amarillo>gris>verde, luego dias_sin_exito desc
    }
    ```
  - cada cliente: `{"taxpayer_id": int, "razon_social": str|None, "cuit": str|None, "estado": "verde"|"amarillo"|"rojo"|"gris", "dias_sin_exito": int|None, "ultima_ok": str|None, "causa_codigo": str|None, "causa_mensaje": str|None, "es_accionable": bool}`
  - `classify(estado_inputs) -> (estado, es_accionable)` — función pura testeable, ver Step 3.

- [ ] **Step 1: Escribir los tests de la función pura `classify` (fallan)**

Crear `backend/tests/unit/test_extraction_health.py`:

```python
from app.services.extraction_health import classify, ACTIONABLE_CODES, RED_THRESHOLD_DAYS


def test_classify_completed_recent_is_green():
    estado, accionable = classify(
        last_status="completed", failure_code=None, dias_sin_exito=0
    )
    assert estado == "verde"
    assert accionable is False


def test_classify_auth_failed_is_red_day_one():
    estado, accionable = classify(
        last_status="failed", failure_code="AUTH_FAILED", dias_sin_exito=1
    )
    assert estado == "rojo"
    assert accionable is True


def test_classify_transient_one_day_is_yellow():
    estado, accionable = classify(
        last_status="failed", failure_code="NETWORK_ERROR", dias_sin_exito=1
    )
    assert estado == "amarillo"
    assert accionable is False


def test_classify_transient_three_days_escalates_to_red():
    estado, accionable = classify(
        last_status="failed", failure_code="NETWORK_ERROR", dias_sin_exito=3
    )
    assert estado == "rojo"
    assert accionable is False  # rojo por antigüedad, no por causa accionable


def test_classify_failed_without_code_is_grey():
    estado, accionable = classify(
        last_status="failed", failure_code=None, dias_sin_exito=5
    )
    assert estado == "gris"
    assert accionable is False


def test_classify_no_jobs_is_grey():
    estado, accionable = classify(
        last_status=None, failure_code=None, dias_sin_exito=None
    )
    assert estado == "gris"
    assert accionable is False


def test_actionable_codes_are_the_red_ones():
    assert ACTIONABLE_CODES == {"AUTH_FAILED", "SERVICE_NOT_ADHERED", "EMPRESA_NOT_FOUND"}


def test_red_threshold_is_three():
    assert RED_THRESHOLD_DAYS == 3
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_health.py -k classify -q`
Expected: FAIL — `ModuleNotFoundError: app.services.extraction_health`.

- [ ] **Step 3: Implementar `classify` y las constantes**

Crear `backend/app/services/extraction_health.py`:

```python
from __future__ import annotations

from ..extensions import db
from ..models import Taxpayer, ExtractionJob
from ..time_utils import now_cordoba_naive

ACTIONABLE_CODES: set[str] = {"AUTH_FAILED", "SERVICE_NOT_ADHERED", "EMPRESA_NOT_FOUND"}
RED_THRESHOLD_DAYS: int = 3

_ESTADO_ORDER = {"rojo": 0, "amarillo": 1, "gris": 2, "verde": 3}


def classify(
    last_status: str | None,
    failure_code: str | None,
    dias_sin_exito: int | None,
) -> tuple[str, bool]:
    """Clasifica el estado de salud de un cliente.

    - verde: último job completed y reciente.
    - rojo: último fallo con causa accionable (AUTH_FAILED / SERVICE_NOT_ADHERED /
      EMPRESA_NOT_FOUND), o causa transitoria que ya lleva >= RED_THRESHOLD_DAYS.
    - amarillo: último fallo con causa transitoria conocida y < RED_THRESHOLD_DAYS.
    - gris: sin jobs, o último fallo sin código (job viejo / causa desconocida).
    """
    if last_status == "completed":
        return ("verde", False)
    if last_status in ("failed", "partial"):
        if failure_code in ACTIONABLE_CODES:
            return ("rojo", True)
        if failure_code is None:
            return ("gris", False)
        # Transitorio conocido.
        if dias_sin_exito is not None and dias_sin_exito >= RED_THRESHOLD_DAYS:
            return ("rojo", False)
        return ("amarillo", False)
    return ("gris", False)
```

- [ ] **Step 4: Correr los tests de `classify`**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_health.py -k classify -q`
Expected: los `classify`/`actionable`/`threshold` PASAN.

- [ ] **Step 5: Escribir los tests de `compute_health` con datos en DB (fallan)**

Append en `backend/tests/unit/test_extraction_health.py`:

```python
from datetime import timedelta
from app.services.extraction_health import compute_health
from app.extensions import db
from app.models import Taxpayer, ExtractionJob
from app.time_utils import now_cordoba_naive


def _mk_taxpayer(app, razon, activo=True):
    with app.app_context():
        t = Taxpayer(razon_social=razon, cuit="20111111110", activo=activo)
        db.session.add(t)
        db.session.commit()
        return t.id


def _mk_job(app, taxpayer_id, status, days_ago, failure_code=None, user_msg=None):
    with app.app_context():
        ts = now_cordoba_naive() - timedelta(days=days_ago)
        j = ExtractionJob(
            taxpayer_id=taxpayer_id,
            operation="scheduler_lpg_extract",
            status=status,
            created_at=ts,
            finished_at=ts,
            failure_code=failure_code,
            failure_message_user=user_msg,
        )
        db.session.add(j)
        db.session.commit()


def test_compute_health_green_for_recent_success(app):
    tid = _mk_taxpayer(app, "Cliente Verde")
    _mk_job(app, tid, "completed", days_ago=0)
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["estado"] == "verde"
    assert row["dias_sin_exito"] == 0


def test_compute_health_red_for_auth_failed(app):
    tid = _mk_taxpayer(app, "Cliente Auth")
    _mk_job(app, tid, "completed", days_ago=8)
    _mk_job(app, tid, "failed", days_ago=1, failure_code="AUTH_FAILED",
            user_msg="La clave fiscal de la empresa parece ser incorrecta.")
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["estado"] == "rojo"
    assert row["es_accionable"] is True
    assert row["causa_codigo"] == "AUTH_FAILED"
    assert row["dias_sin_exito"] == 8


def test_compute_health_never_extracted_is_grey(app):
    tid = _mk_taxpayer(app, "Cliente Nuevo")
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["estado"] == "gris"
    assert row["dias_sin_exito"] is None
    assert row["ultima_ok"] is None


def test_compute_health_excludes_inactive(app):
    tid = _mk_taxpayer(app, "Cliente Inactivo", activo=False)
    _mk_job(app, tid, "failed", days_ago=1, failure_code="AUTH_FAILED")
    with app.app_context():
        out = compute_health()
    assert all(c["taxpayer_id"] != tid for c in out["clientes"])


def test_compute_health_resumen_counts(app):
    out_tid = _mk_taxpayer(app, "Cliente Resumen")
    _mk_job(app, out_tid, "completed", days_ago=0)
    with app.app_context():
        out = compute_health()
    assert out["resumen"]["verde"] >= 1
    assert set(out["resumen"].keys()) == {"verde", "amarillo", "rojo", "gris"}
```

> Nota: el fixture `app` provee SQLite in-memory por test (ver `backend/tests/conftest.py`). Si `Taxpayer` requiere campos obligatorios adicionales (revisar el modelo), agregarlos en `_mk_taxpayer`.

- [ ] **Step 6: Correr y verificar que fallan**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_health.py -k compute_health -q`
Expected: FAIL — `compute_health` no existe.

- [ ] **Step 7: Implementar `compute_health`**

Agregar a `backend/app/services/extraction_health.py`:

```python
def _dias_sin_exito(ultima_ok) -> int | None:
    if ultima_ok is None:
        return None
    hoy = now_cordoba_naive().date()
    return (hoy - ultima_ok.date()).days


def compute_health() -> dict:
    taxpayers = (
        Taxpayer.query.filter(Taxpayer.activo == True)  # noqa: E712
        .order_by(Taxpayer.id)
        .all()
    )
    clientes: list[dict] = []
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0, "gris": 0}

    for t in taxpayers:
        last_job = (
            ExtractionJob.query.filter(ExtractionJob.taxpayer_id == t.id)
            .order_by(ExtractionJob.created_at.desc())
            .first()
        )
        ultima_ok_job = (
            ExtractionJob.query.filter(
                ExtractionJob.taxpayer_id == t.id,
                ExtractionJob.status == "completed",
                ExtractionJob.finished_at.isnot(None),
            )
            .order_by(ExtractionJob.finished_at.desc())
            .first()
        )
        ultima_ok = ultima_ok_job.finished_at if ultima_ok_job else None
        dias = _dias_sin_exito(ultima_ok)

        last_status = last_job.status if last_job else None
        failure_code = last_job.failure_code if last_job else None
        estado, accionable = classify(last_status, failure_code, dias)

        es_fallo = last_status in ("failed", "partial")
        clientes.append(
            {
                "taxpayer_id": t.id,
                "razon_social": t.razon_social,
                "cuit": t.cuit,
                "estado": estado,
                "dias_sin_exito": dias,
                "ultima_ok": ultima_ok.date().isoformat() if ultima_ok else None,
                "causa_codigo": failure_code if es_fallo else None,
                "causa_mensaje": (last_job.failure_message_user if es_fallo else None),
                "es_accionable": accionable,
            }
        )
        resumen[estado] += 1

    clientes.sort(
        key=lambda c: (
            _ESTADO_ORDER[c["estado"]],
            -(c["dias_sin_exito"] or 0),
        )
    )

    return {
        "generado_en": now_cordoba_naive().isoformat(),
        "resumen": resumen,
        "clientes": clientes,
    }
```

- [ ] **Step 8: Correr todo el archivo**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_health.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/extraction_health.py backend/tests/unit/test_extraction_health.py
git commit -m "feat(extracciones): servicio de clasificación de salud por cliente"
```

---

## Task 5: Endpoint `GET /api/extracciones/salud`

**Files:**
- Create: `backend/app/api/extracciones.py`
- Modify: `backend/app/api/__init__.py`
- Test: `backend/tests/unit/test_extraccion_salud_endpoint.py`

**Interfaces:**
- Consumes: `compute_health()` (Task 4), `require_auth`.
- Produces: `GET /api/extracciones/salud` → JSON de `compute_health()` con 200; 401 sin auth.

- [ ] **Step 1: Escribir el test del endpoint (falla)**

Crear `backend/tests/unit/test_extraccion_salud_endpoint.py`:

```python
def test_salud_requires_auth(client):
    res = client.get("/api/extracciones/salud")
    assert res.status_code == 401


def test_salud_returns_shape(client, auth_headers):
    res = client.get("/api/extracciones/salud", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert "resumen" in data
    assert "clientes" in data
    assert "generado_en" in data
    assert set(data["resumen"].keys()) == {"verde", "amarillo", "rojo", "gris"}
```

> Verificar en `backend/tests/conftest.py` cómo se llama el fixture de headers autenticados (puede ser `auth_headers`, `authenticated_client`, etc.). Usar el que exista; si los tests de `clients.py` ya hacen requests autenticados, copiar ese patrón exacto.

- [ ] **Step 2: Correr para verificar que falla**

Run: `cd backend && python3 -m pytest tests/unit/test_extraccion_salud_endpoint.py -q`
Expected: FAIL — 404 (ruta no existe) en el test de shape.

- [ ] **Step 3: Crear el blueprint**

Crear `backend/app/api/extracciones.py`:

```python
from __future__ import annotations

from flask import Blueprint, jsonify

from ..middleware import require_auth
from ..services.extraction_health import compute_health

extracciones_bp = Blueprint("extracciones", __name__)


@extracciones_bp.get("/extracciones/salud")
@require_auth
def get_extracciones_salud():
    """Estado de salud de las extracciones por cliente activo."""
    return jsonify(compute_health())
```

- [ ] **Step 4: Registrar el blueprint**

En `backend/app/api/__init__.py`:
- agregar el import junto a los otros (al inicio, donde están los `from .xxx import xxx_bp`): `from .extracciones import extracciones_bp`
- agregar el registro junto a los otros en `register_blueprints`: `app.register_blueprint(extracciones_bp, url_prefix="/api")`

- [ ] **Step 5: Correr el test del endpoint**

Run: `cd backend && python3 -m pytest tests/unit/test_extraccion_salud_endpoint.py -q`
Expected: PASS.

- [ ] **Step 6: Smoke test contra la DB real (datos de prod)**

Asegurarse de que el stack está arriba (`make up`) y la migración aplicada. Obtener un token y consultar (ajustar el login al patrón real del proyecto; si hay un usuario seed, usarlo):

Run: `curl -s http://localhost:5001/api/extracciones/salud -H "Authorization: Bearer <token>" | python3 -m json.tool | head -40`
Expected: el cliente id=30 aparece en `rojo` con `causa_codigo: "AUTH_FAILED"` (último fallo) o `timeout` escalado; el id=6 en `gris` con `ultima_ok: null`.

> Si obtener el token es fricción, este smoke test es opcional — la cobertura real la dan los tests de Task 4. No bloquear el avance por esto.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/extracciones.py backend/app/api/__init__.py backend/tests/unit/test_extraccion_salud_endpoint.py
git commit -m "feat(extracciones): endpoint GET /extracciones/salud"
```

---

## Task 6: Cliente HTTP y hook frontend

**Files:**
- Create: `frontend/src/api/extracciones.ts`
- Create: `frontend/src/hooks/useExtractionHealth.ts`

**Interfaces:**
- Consumes: `fetchWithAuth` de `./client` (mismo patrón que `api/stats.ts`).
- Produces:
  - tipos `ExtractionHealthEstado = "verde" | "amarillo" | "rojo" | "gris"`, `ClienteSalud`, `ExtractionHealth`
  - `getExtractionHealth(): Promise<ExtractionHealth>`
  - `useExtractionHealthQuery()` — TanStack Query hook, queryKey `["extraction-health"]`

- [ ] **Step 1: Crear el cliente HTTP + tipos**

Crear `frontend/src/api/extracciones.ts`:

```typescript
import { fetchWithAuth } from "./client";

export type ExtractionHealthEstado = "verde" | "amarillo" | "rojo" | "gris";

export interface ClienteSalud {
  taxpayer_id: number;
  razon_social: string | null;
  cuit: string | null;
  estado: ExtractionHealthEstado;
  dias_sin_exito: number | null;
  ultima_ok: string | null;
  causa_codigo: string | null;
  causa_mensaje: string | null;
  es_accionable: boolean;
}

export interface ExtractionHealth {
  generado_en: string;
  resumen: Record<ExtractionHealthEstado, number>;
  clientes: ClienteSalud[];
}

export async function getExtractionHealth(): Promise<ExtractionHealth> {
  const res = await fetchWithAuth("/extracciones/salud");
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error ?? "Error al obtener la salud de extracciones");
  }
  return data;
}
```

- [ ] **Step 2: Crear el hook**

Crear `frontend/src/hooks/useExtractionHealth.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { getExtractionHealth, type ExtractionHealth } from "../api/extracciones";

export function useExtractionHealthQuery() {
  return useQuery<ExtractionHealth, Error>({
    queryKey: ["extraction-health"],
    queryFn: () => getExtractionHealth(),
  });
}
```

- [ ] **Step 3: Type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/extracciones.ts frontend/src/hooks/useExtractionHealth.ts
git commit -m "feat(extracciones): cliente HTTP y hook de salud de extracciones"
```

---

## Task 7: Página "Salud de extracciones"

**Files:**
- Create: `frontend/src/pages/ExtractionHealthPage.tsx`
- Modify: navegación/router existente (ver Step 4)

**Interfaces:**
- Consumes: `useExtractionHealthQuery()` (Task 6), tipos de `api/extracciones`.

- [ ] **Step 1: Identificar el patrón de página y router**

Run: `ls frontend/src/pages && grep -rn "Route\|createBrowserRouter\|path:" frontend/src/App.tsx frontend/src/main.tsx 2>/dev/null | head`
Leer `frontend/src/pages/ClientsPage.tsx` para copiar el layout (encabezado, contenedor, estados loading/error). Identificar dónde se declaran las rutas y el menú de navegación.

- [ ] **Step 2: Crear la página**

Crear `frontend/src/pages/ExtractionHealthPage.tsx`. Seguir el layout de `ClientsPage`. Estructura mínima:

```typescript
import { useExtractionHealthQuery } from "../hooks/useExtractionHealth";
import type { ExtractionHealthEstado } from "../api/extracciones";

const ESTADO_LABEL: Record<ExtractionHealthEstado, string> = {
  verde: "OK",
  amarillo: "Atención",
  rojo: "Acción requerida",
  gris: "Sin datos",
};

const ESTADO_COLOR: Record<ExtractionHealthEstado, string> = {
  verde: "bg-green-100 text-green-800",
  amarillo: "bg-yellow-100 text-yellow-800",
  rojo: "bg-red-100 text-red-800",
  gris: "bg-gray-100 text-gray-700",
};

export default function ExtractionHealthPage() {
  const { data, isLoading, error } = useExtractionHealthQuery();

  if (isLoading) return <div className="p-6">Cargando salud de extracciones…</div>;
  if (error) return <div className="p-6 text-red-700">{error.message}</div>;
  if (!data) return null;

  const { resumen, clientes } = data;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Salud de extracciones</h1>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {(["rojo", "amarillo", "gris", "verde"] as ExtractionHealthEstado[]).map(
          (estado) => (
            <div key={estado} className={`rounded-lg p-4 ${ESTADO_COLOR[estado]}`}>
              <div className="text-sm">{ESTADO_LABEL[estado]}</div>
              <div className="text-3xl font-bold">{resumen[estado]}</div>
            </div>
          )
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2">Empresa</th>
              <th className="px-3 py-2">CUIT</th>
              <th className="px-3 py-2">Días sin éxito</th>
              <th className="px-3 py-2">Causa</th>
              <th className="px-3 py-2">Última extracción OK</th>
            </tr>
          </thead>
          <tbody>
            {clientes.map((c) => (
              <tr key={c.taxpayer_id} className="border-t">
                <td className="px-3 py-2">
                  <span
                    className={`inline-block rounded-full px-2 py-0.5 text-xs ${ESTADO_COLOR[c.estado]}`}
                  >
                    {ESTADO_LABEL[c.estado]}
                  </span>
                </td>
                <td className="px-3 py-2">{c.razon_social ?? "—"}</td>
                <td className="px-3 py-2">{c.cuit ?? "—"}</td>
                <td className="px-3 py-2">
                  {c.dias_sin_exito === null ? "Nunca" : c.dias_sin_exito}
                </td>
                <td className="px-3 py-2 max-w-md">
                  {c.estado === "verde" ? "—" : c.causa_mensaje ?? "Causa desconocida"}
                </td>
                <td className="px-3 py-2">{c.ultima_ok ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Type check de la página**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 4: Registrar la ruta y el ítem de menú**

Siguiendo el patrón detectado en Step 1, agregar:
- la ruta (ej. `/salud-extracciones`) apuntando a `ExtractionHealthPage`
- un ítem en el menú de navegación con label "Salud de extracciones"

Copiar exactamente la forma en que se declara otra página existente (ej. la de stats/dashboard). No inventar un router nuevo.

- [ ] **Step 5: Build completo**

Run: `cd frontend && npm run build`
Expected: build OK sin errores de tipo.

- [ ] **Step 6: Verificación visual en el navegador**

Con el stack arriba (`make up`), abrir `http://localhost:5173`, loguearse, navegar a "Salud de extracciones". Verificar: cards de resumen con conteos, tabla ordenada con rojos arriba, el cliente caído por clave fiscal mostrando su causa accionable.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ExtractionHealthPage.tsx frontend/src/App.tsx
git commit -m "feat(extracciones): página de salud de extracciones"
```

> Ajustar los paths del `git add` a los archivos de router/menú reales que se hayan tocado en Step 4.

---

## Task 8: Verificación integral y PR

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && python3 -m pytest tests/ -q`
Expected: todo verde (incluyendo los 246 previos + los nuevos).

- [ ] **Step 2: Compile check backend**

Run: `cd backend && python3 -m compileall app -q && echo OK`
Expected: `OK`.

- [ ] **Step 3: Frontend type check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: ambos OK.

- [ ] **Step 4: Fresh-context code review del diff**

Antes del PR, correr una revisión adversarial del diff completo de la rama contra `dev` (regla de revisión fresca del proyecto).

- [ ] **Step 5: Push y PR a dev**

```bash
git push -u origin feature/076-panel-salud-extracciones
gh pr create --base dev --head feature/076-panel-salud-extracciones \
  --title "feat(extracciones): panel de salud de extracciones" \
  --body "Implementa el panel read-only de salud de extracciones por cliente. Closes spec 2026-06-23-panel-salud-extracciones-design."
```
Expected: PR creado, CI en verde.

---

## Self-Review

**Spec coverage:**
- Columna `failure_code` → Task 2. ✅
- `map_failure` devuelve código → Task 1. ✅
- Persistencia del código (worker + stale) → Task 3. ✅
- Lógica de semáforo (verde/amarillo/rojo/gris + escalado a 3 días + accionable) → Task 4 (`classify`). ✅
- Agregación por cliente (último job, ultima_ok, dias_sin_exito, ordenamiento, exclusión inactivos) → Task 4 (`compute_health`). ✅
- Endpoint `GET /api/extracciones/salud` con auth → Task 5. ✅
- Manejo de jobs viejos sin código (gris) → cubierto en `classify` y testeado (Task 4 Step 1). ✅
- Frontend: cards resumen + tabla ordenada + causa accionable → Tasks 6-7. ✅
- Testing backend (casos de la data real) + frontend tsc/build → Tasks 4, 5, 8. ✅
- No backfill de históricos → implícito: jobs viejos quedan en gris, ningún task los toca. ✅

**Placeholder scan:** sin TBD/TODO; todo paso de código muestra el código. Los puntos marcados "leer antes de editar" / "ajustar al patrón real" son por números de línea aproximados en archivos grandes y patrones de fixture/router que varían — no son placeholders de lógica.

**Type consistency:**
- `map_failure -> tuple[str, str, str]` consistente entre Task 1 (def) y Task 3 (consumo).
- `classify(last_status, failure_code, dias_sin_exito) -> (estado, bool)` consistente entre Task 4 def, sus tests y `compute_health`.
- Forma de `ClienteSalud` consistente entre el endpoint (Task 4/5) y los tipos TS (Task 6) y su uso en la página (Task 7): `taxpayer_id`, `razon_social`, `cuit`, `estado`, `dias_sin_exito`, `ultima_ok`, `causa_codigo`, `causa_mensaje`, `es_accionable`.
- `resumen` keys `{verde, amarillo, rojo, gris}` consistentes backend↔frontend.
