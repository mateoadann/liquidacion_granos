# Auto-bloqueo del scheduler ante clave incorrecta (079) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evitar que un cliente con clave fiscal incorrecta dispare el captcha anti-bot de AFIP, pausando el scheduler al primer `AUTH_FAILED` y reactivándolo automáticamente solo cuando la clave fiscal se actualiza.

**Architecture:** Dos columnas nuevas en `taxpayer` (`clave_fiscal_actualizada_en`, `scheduler_pausado_por_auth`). El worker pausa el cliente al detectar `failure_code=AUTH_FAILED` en un job de scheduler. El tick del scheduler reactiva los pausados-por-auth cuya clave fue actualizada después del error. Los endpoints que cambian la clave estampan `clave_fiscal_actualizada_en`.

**Tech Stack:** Flask + SQLAlchemy + Alembic, pytest.

## Global Constraints

- Timestamps en timezone America/Argentina/Cordoba (`now_cordoba_naive()` de `app/time_utils.py`).
- `from __future__ import annotations` en módulos tipados nuevos (las migraciones siguen el patrón Alembic estándar, sin esa línea).
- DB pattern: `db.session.add()` + `db.session.commit()`.
- Comandos de test: backend `cd backend && python3 -m pytest <ruta> -q` (el binario es `python3`, no `python`).
- `failure_code` conocidos: `AUTH_FAILED`, `SERVICE_NOT_ADHERED`, `EMPRESA_NOT_FOUND`, `TRANSIENT_LOGIN`, `NETWORK_ERROR`, `WS_COE_ERRORS`, `UNKNOWN_ERROR`, etc. (de `extraction_failure_mapper`).
- El bloqueo aplica SOLO a `failure_code == "AUTH_FAILED"` y SOLO a operations de scheduler (prefijo en `SCHEDULER_OPERATION_PREFIX`).
- Head de migraciones actual: `20260623_0015`.

---

## File Structure

| Archivo | Responsabilidad |
|---------|-----------------|
| `backend/app/models/taxpayer.py` | columnas `clave_fiscal_actualizada_en`, `scheduler_pausado_por_auth` |
| `backend/migrations/versions/20260623_0016_*.py` | migración de las 2 columnas |
| `backend/app/api/clients.py` | estampar `clave_fiscal_actualizada_en` al cambiar la clave (2 lugares) |
| `backend/app/workers/playwright_jobs.py` | bloqueo en `_actualizar_scheduler_status` |
| `backend/app/services/scheduler_service.py` | reactivación al inicio de `tick_scheduler` |
| `backend/tests/unit/test_scheduler_auto_block.py` | **nuevo** — tests de bloqueo + reactivación |
| `backend/tests/unit/test_clients_*` | test del estampado de timestamp |

---

## Task 1: Columnas en el modelo + migración

**Files:**
- Modify: `backend/app/models/taxpayer.py`
- Create: `backend/migrations/versions/20260623_0016_add_auth_block_fields.py`

**Interfaces:**
- Produces: `Taxpayer.clave_fiscal_actualizada_en: datetime | None`, `Taxpayer.scheduler_pausado_por_auth: bool` (NOT NULL, default False).

- [ ] **Step 1: Agregar los campos al modelo**

En `backend/app/models/taxpayer.py`, después de `scheduler_ultimo_error_en` (línea ~30), agregar:

```python
    clave_fiscal_actualizada_en = db.Column(db.DateTime, nullable=True)
    scheduler_pausado_por_auth = db.Column(
        db.Boolean, nullable=False, default=False, server_default="false"
    )
```

> `server_default="false"` es necesario para que la columna NOT NULL se aplique a las
> filas existentes durante la migración.

- [ ] **Step 2: Crear la migración**

Crear `backend/migrations/versions/20260623_0016_add_auth_block_fields.py`:

```python
"""Add auth-block fields to taxpayer.

clave_fiscal_actualizada_en: timestamp del último cambio de la clave fiscal,
para reactivar el scheduler solo cuando la credencial se actualizó.
scheduler_pausado_por_auth: distingue pausa automática por AUTH_FAILED
(auto-reactivable) de pausa manual.

Revision ID: 20260623_0016
Revises: 20260623_0015
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "20260623_0016"
down_revision = "20260623_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "taxpayer",
        sa.Column("clave_fiscal_actualizada_en", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "taxpayer",
        sa.Column(
            "scheduler_pausado_por_auth",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("taxpayer", "scheduler_pausado_por_auth")
    op.drop_column("taxpayer", "clave_fiscal_actualizada_en")
```

> Antes de fijar `down_revision`, confirmar el head con:
> `cd backend && python3 -c "import glob,re; [print(re.search(r'revision\s*=\s*[\"\x27]([^\"\x27]+)', open(f).read()).group(1)) for f in glob.glob('migrations/versions/*.py')]" | sort | tail`
> Head esperado: `20260623_0015`.

- [ ] **Step 3: Aplicar la migración localmente**

Run: `docker exec liquidacion_granos-backend-1 flask --app run.py db upgrade` (o `make db-upgrade` si el venv local está completo).
Expected: aplica `20260623_0016` sin error.

- [ ] **Step 4: Verificar las columnas**

Run: `docker exec liquidacion_granos-postgres-1 psql -U liquidacion -d liquidacion_granos -c "\d taxpayer" | grep -E "clave_fiscal_actualizada_en|scheduler_pausado_por_auth"`
Expected: ambas columnas presentes.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/taxpayer.py backend/migrations/versions/20260623_0016_add_auth_block_fields.py
git commit -m "feat(scheduler): columnas para auto-bloqueo por clave incorrecta"
```

---

## Task 2: Estampar `clave_fiscal_actualizada_en` al cambiar la clave

**Files:**
- Modify: `backend/app/api/clients.py`
- Test: `backend/tests/unit/test_clients_clave_timestamp.py`

**Interfaces:**
- Consumes: `Taxpayer.clave_fiscal_actualizada_en` (Task 1), `now_cordoba_naive`.
- Produces: cambiar la clave fiscal (endpoint subir-clave o PATCH con `clave_fiscal`) setea `clave_fiscal_actualizada_en`.

> Contexto: hay dos asignaciones de `item.clave_fiscal_encrypted` en `clients.py`
> (líneas ~346 y ~424). Ubicar por contenido (`item.clave_fiscal_encrypted =`).
> Verificar que `now_cordoba_naive` esté importado; si no, agregarlo desde `..time_utils`.

- [ ] **Step 1: Escribir los tests (fallan)**

Crear `backend/tests/unit/test_clients_clave_timestamp.py`. Usar el patrón de auth de los
otros tests de clients (revisar `conftest.py` para el fixture de headers autenticados; si
los tests de clients usan `auth_headers`, usar ese):

```python
from app.models import Taxpayer
from app.extensions import db


def _crear_cliente(app):
    with app.app_context():
        t = Taxpayer(empresa="Test SA", cuit="20111111110", cuit_representado="30111111110")
        db.session.add(t)
        db.session.commit()
        return t.id


def test_patch_clave_sets_timestamp(app, client, auth_headers):
    tid = _crear_cliente(app)
    res = client.patch(
        f"/api/clients/{tid}",
        json={"clave_fiscal": "nueva-clave-123"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    with app.app_context():
        t = Taxpayer.query.get(tid)
        assert t.clave_fiscal_actualizada_en is not None


def test_patch_without_clave_does_not_set_timestamp(app, client, auth_headers):
    tid = _crear_cliente(app)
    res = client.patch(
        f"/api/clients/{tid}",
        json={"empresa": "Otro Nombre SA"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    with app.app_context():
        t = Taxpayer.query.get(tid)
        assert t.clave_fiscal_actualizada_en is None
```

> Si el modelo `Taxpayer` exige campos NOT NULL adicionales al crearlo, agregarlos en
> `_crear_cliente` (revisar `backend/app/models/taxpayer.py`). Si el PATCH de clave exige
> otros campos en el payload, ajustar el request al contrato real del endpoint.

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd backend && python3 -m pytest tests/unit/test_clients_clave_timestamp.py -q`
Expected: FAIL — `clave_fiscal_actualizada_en` queda None al cambiar la clave.

- [ ] **Step 3: Estampar el timestamp en ambos lugares**

En `backend/app/api/clients.py`, en cada lugar donde se asigna `item.clave_fiscal_encrypted`
(líneas ~346 y ~424), agregar inmediatamente después:

```python
    item.clave_fiscal_actualizada_en = now_cordoba_naive()
```

Asegurar el import al inicio del archivo (si no existe):
```python
from ..time_utils import now_cordoba_naive
```

- [ ] **Step 4: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_clients_clave_timestamp.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/clients.py backend/tests/unit/test_clients_clave_timestamp.py
git commit -m "feat(clientes): estampar fecha de cambio de clave fiscal"
```

---

## Task 3: Bloqueo en el worker ante AUTH_FAILED

**Files:**
- Modify: `backend/app/workers/playwright_jobs.py`
- Test: `backend/tests/unit/test_scheduler_auto_block.py`

**Interfaces:**
- Consumes: `Taxpayer.scheduler_activo`, `Taxpayer.scheduler_pausado_por_auth` (Task 1), `job.failure_code`.
- Produces: tras un job de scheduler `failed` con `failure_code=="AUTH_FAILED"`, el taxpayer queda `scheduler_activo=False`, `scheduler_pausado_por_auth=True`.

> Contexto: `_actualizar_scheduler_status(job, *, final_status, error_text)` (línea ~194)
> ya filtra por `SCHEDULER_OPERATION_PREFIX` y carga el `taxpayer`. El bloqueo va en la
> rama de error (`final_status not in {"completed","partial"}`), leyendo `job.failure_code`.

- [ ] **Step 1: Escribir el test (falla)**

Crear `backend/tests/unit/test_scheduler_auto_block.py`:

```python
from app.extensions import db
from app.models import Taxpayer, ExtractionJob
from app.workers.playwright_jobs import _actualizar_scheduler_status


def _mk_taxpayer(app, **kwargs):
    with app.app_context():
        defaults = dict(empresa="Test SA", cuit="20111111110",
                        cuit_representado="30111111110", scheduler_activo=True)
        defaults.update(kwargs)
        t = Taxpayer(**defaults)
        db.session.add(t)
        db.session.commit()
        return t.id


def _mk_job(app, taxpayer_id, operation, failure_code):
    with app.app_context():
        j = ExtractionJob(taxpayer_id=taxpayer_id, operation=operation,
                          status="failed", failure_code=failure_code)
        db.session.add(j)
        db.session.commit()
        return ExtractionJob.query.get(j.id)


def test_auth_failed_blocks_scheduler(app):
    tid = _mk_taxpayer(app)
    with app.app_context():
        job = _mk_job(app, tid, "scheduler_lpg_extract", "AUTH_FAILED")
        _actualizar_scheduler_status(job, final_status="failed", error_text="clave mal")
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is False
        assert t.scheduler_pausado_por_auth is True


def test_timeout_does_not_block(app):
    tid = _mk_taxpayer(app)
    with app.app_context():
        job = _mk_job(app, tid, "scheduler_lpg_extract", "TRANSIENT_LOGIN")
        _actualizar_scheduler_status(job, final_status="failed", error_text="timeout")
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is True
        assert t.scheduler_pausado_por_auth is False


def test_manual_auth_failed_does_not_block(app):
    tid = _mk_taxpayer(app)
    with app.app_context():
        job = _mk_job(app, tid, "playwright_lpg_run", "AUTH_FAILED")
        _actualizar_scheduler_status(job, final_status="failed", error_text="clave mal")
        t = Taxpayer.query.get(tid)
        # operation no-scheduler: el hook retorna temprano, no toca el scheduler
        assert t.scheduler_activo is True
        assert t.scheduler_pausado_por_auth is False
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `cd backend && python3 -m pytest tests/unit/test_scheduler_auto_block.py -q`
Expected: FAIL — `test_auth_failed_blocks_scheduler` falla (scheduler_activo sigue True).

- [ ] **Step 3: Implementar el bloqueo**

En `_actualizar_scheduler_status` (`playwright_jobs.py`), en la rama `else` (error), después
de setear `scheduler_ultimo_error` / `scheduler_ultimo_error_en` y ANTES del `db.session.commit()`:

```python
        if job.failure_code == "AUTH_FAILED":
            taxpayer.scheduler_activo = False
            taxpayer.scheduler_pausado_por_auth = True
            logger.warning(
                "SCHEDULER_AUTO_BLOCKED | taxpayer_id=%s job_id=%s reason=auth_failed",
                taxpayer.id,
                job.id,
            )
```

- [ ] **Step 4: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_scheduler_auto_block.py -q`
Expected: PASS (los 3).

- [ ] **Step 5: Compile + suite de workers (no romper nada)**

Run: `cd backend && python3 -m compileall app -q && python3 -m pytest tests/unit/test_playwright_jobs_failure_code.py tests/unit/test_scheduler_defaults.py -q`
Expected: OK + PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/playwright_jobs.py backend/tests/unit/test_scheduler_auto_block.py
git commit -m "feat(scheduler): pausar cliente al detectar clave incorrecta"
```

---

## Task 4: Reactivación en el tick del scheduler

**Files:**
- Modify: `backend/app/services/scheduler_service.py`
- Test: `backend/tests/unit/test_scheduler_auto_block.py` (extender)

**Interfaces:**
- Consumes: `scheduler_pausado_por_auth`, `clave_fiscal_actualizada_en`, `scheduler_ultimo_error_en` (Task 1).
- Produces: `reactivar_pausados_por_auth() -> int` (cantidad reactivada), llamada al inicio de `tick_scheduler()`.

> Contexto: `tick_scheduler()` (línea ~29) selecciona con
> `Taxpayer.query.filter_by(scheduler_activo=True, activo=True)` (línea ~46). La
> reactivación debe correr ANTES de esa query, para que un cliente recién reactivado
> entre en la selección del mismo tick.

- [ ] **Step 1: Escribir los tests de reactivación (fallan)**

Agregar a `backend/tests/unit/test_scheduler_auto_block.py`:

```python
from datetime import timedelta
from app.time_utils import now_cordoba_naive
from app.services.scheduler_service import reactivar_pausados_por_auth


def test_reactivates_when_clave_updated_after_error(app):
    ahora = now_cordoba_naive()
    tid = _mk_taxpayer(
        app,
        scheduler_activo=False,
        scheduler_pausado_por_auth=True,
        scheduler_ultimo_error_en=ahora - timedelta(days=2),
        clave_fiscal_actualizada_en=ahora,  # clave actualizada DESPUÉS del error
    )
    with app.app_context():
        n = reactivar_pausados_por_auth()
        t = Taxpayer.query.get(tid)
        assert n == 1
        assert t.scheduler_activo is True
        assert t.scheduler_pausado_por_auth is False


def test_no_reactivate_when_clave_not_updated(app):
    ahora = now_cordoba_naive()
    tid = _mk_taxpayer(
        app,
        scheduler_activo=False,
        scheduler_pausado_por_auth=True,
        scheduler_ultimo_error_en=ahora,
        clave_fiscal_actualizada_en=ahora - timedelta(days=2),  # clave vieja
    )
    with app.app_context():
        reactivar_pausados_por_auth()
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is False
        assert t.scheduler_pausado_por_auth is True


def test_no_reactivate_manual_pause(app):
    ahora = now_cordoba_naive()
    tid = _mk_taxpayer(
        app,
        scheduler_activo=False,
        scheduler_pausado_por_auth=False,  # pausa MANUAL
        scheduler_ultimo_error_en=ahora - timedelta(days=2),
        clave_fiscal_actualizada_en=ahora,
    )
    with app.app_context():
        reactivar_pausados_por_auth()
        t = Taxpayer.query.get(tid)
        assert t.scheduler_activo is False  # no se toca
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd backend && python3 -m pytest tests/unit/test_scheduler_auto_block.py -k reactiv -q`
Expected: FAIL — `reactivar_pausados_por_auth` no existe.

- [ ] **Step 3: Implementar la reactivación**

En `backend/app/services/scheduler_service.py`, agregar la función (antes de `tick_scheduler`):

```python
def reactivar_pausados_por_auth() -> int:
    """Reactiva clientes pausados automáticamente por AUTH_FAILED cuya clave
    fiscal fue actualizada después del error. Devuelve la cantidad reactivada.

    No toca pausas manuales (scheduler_pausado_por_auth=False).
    """
    candidatos = Taxpayer.query.filter_by(
        scheduler_pausado_por_auth=True, activo=True
    ).all()
    reactivados = 0
    for t in candidatos:
        if (
            t.clave_fiscal_actualizada_en is not None
            and t.scheduler_ultimo_error_en is not None
            and t.clave_fiscal_actualizada_en > t.scheduler_ultimo_error_en
        ):
            t.scheduler_activo = True
            t.scheduler_pausado_por_auth = False
            reactivados += 1
            logger.info(
                "SCHEDULER_AUTO_REACTIVATED | taxpayer_id=%s", t.id
            )
    if reactivados:
        db.session.commit()
    return reactivados
```

Luego, en `tick_scheduler()`, como PRIMERA línea del cuerpo (antes de `now = now_cordoba_naive()`):

```python
    reactivar_pausados_por_auth()
```

> Verificar que `logger` y `db` ya están importados en el módulo (lo están: el módulo ya
> los usa). `Taxpayer` también ya está importado.

- [ ] **Step 4: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_scheduler_auto_block.py -q`
Expected: PASS (todos: bloqueo + reactivación).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scheduler_service.py backend/tests/unit/test_scheduler_auto_block.py
git commit -m "feat(scheduler): reactivar cliente al actualizar la clave fiscal"
```

---

## Task 5: Verificación integral y PR

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && python3 -m pytest tests/ -q`
Expected: todo verde.

- [ ] **Step 2: Compile check**

Run: `cd backend && python3 -m compileall app -q && echo OK`
Expected: `OK`.

- [ ] **Step 3: Fresh-context code review del diff contra dev.**

- [ ] **Step 4: Push y PR a dev**

```bash
git push -u origin feature/079-auto-bloqueo-auth-failed
gh pr create --base dev --head feature/079-auto-bloqueo-auth-failed \
  --title "feat(scheduler): auto-bloqueo ante clave incorrecta" \
  --body "Pausa el scheduler al primer AUTH_FAILED y lo reactiva al actualizar la clave fiscal. Previene el embudo clave-incorrecta → captcha de AFIP. Closes spec 2026-06-23-auto-bloqueo-auth-failed-design."
```
Expected: PR creado, CI en verde.

---

## Self-Review

**Spec coverage:**
- Columnas `clave_fiscal_actualizada_en` + `scheduler_pausado_por_auth` → Task 1. ✅
- Estampar timestamp al cambiar clave (2 lugares, no otras ediciones) → Task 2. ✅
- Bloqueo al primer AUTH_FAILED, solo scheduler, solo ese código → Task 3. ✅
- Desbloqueo solo si clave actualizada > error; no reactivar pausa manual → Task 4. ✅
- Tests de todos los casos del spec → Tasks 2, 3, 4. ✅
- Caso Erlina (enfriamiento manual) → fuera de scope, lo maneja el usuario (documentado en spec). ✅

**Placeholder scan:** sin TBD/TODO; cada step de código muestra el código. Las notas
"ubicar por contenido" son por números de línea aproximados, no placeholders de lógica.

**Type consistency:**
- `reactivar_pausados_por_auth() -> int` consistente entre Task 4 (def), su llamada en
  `tick_scheduler` y los tests.
- `scheduler_pausado_por_auth: bool` y `clave_fiscal_actualizada_en: datetime|None`
  consistentes entre Task 1 (modelo), Task 2 (seteo), Task 3 (bloqueo) y Task 4 (lectura).
- `job.failure_code == "AUTH_FAILED"` consistente con el código persistido por la 077.
