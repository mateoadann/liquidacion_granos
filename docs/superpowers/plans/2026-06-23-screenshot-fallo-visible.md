# Screenshot de fallo visible en la UI (080) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar en el `JobDetailDrawer` el screenshot que el robot captura al fallar (login con captcha, búsqueda de servicio), persistiéndolo en la DB y purgándolo automáticamente tras N días.

**Architecture:** El screenshot (bytes PNG) viaja del cliente Playwright al worker vía `TaxpayerPipelineResult`; el worker lo guarda como base64 en una tabla nueva `job_screenshot` (patrón `pdf_cache`). Un endpoint con auth lo sirve; el drawer lo muestra cargándolo como blob (patrón del PDF de COE). Una purga periódica borra los de más de 3 días.

**Tech Stack:** Flask + SQLAlchemy + Alembic, pytest, React 18 + TypeScript + TanStack Query.

## Global Constraints

- Timestamps timezone America/Argentina/Cordoba (`now_cordoba_naive()` de `app/time_utils.py`).
- Endpoints protegidos con `@require_auth` (de `app.middleware`).
- Errores de API: `{"error": "..."}` con status apropiado.
- `from __future__ import annotations` en módulos tipados nuevos (migraciones siguen patrón Alembic estándar).
- DB pattern: `db.session.add()` + `db.session.commit()`.
- Servir binarios: `send_file(io.BytesIO(bytes), mimetype=...)` (patrón `download_coe_pdf` en `coes.py`).
- Frontend descarga binarios con `fetchWithAuth` → `Blob` → `URL.createObjectURL` (NO `<img src>` plano: `fetchWithAuth` agrega header Bearer que un `<img>` no lleva). Patrón: `downloadCoePdf` en `api/coes.ts`.
- TypeScript estricto, 2-space, double quotes, semicolons.
- Comandos de test: backend `cd backend && python3 -m pytest <ruta> -q` (binario `python3`); frontend `cd frontend && npx tsc --noEmit` y `npm run build`.
- Head de migraciones actual: `20260623_0016`.
- Retención de screenshots: `SCREENSHOT_RETENTION_DAYS` default 3.

---

## File Structure

| Archivo | Responsabilidad |
|---------|-----------------|
| `backend/app/models/job_screenshot.py` | modelo `JobScreenshot` (base64) |
| `backend/app/models/__init__.py` | exportar `JobScreenshot` |
| `backend/migrations/versions/20260623_0017_*.py` | tabla `job_screenshot` |
| `backend/app/services/lpg_playwright_pipeline.py` | campo `failure_screenshot_png` en `TaxpayerPipelineResult` |
| `backend/app/integrations/playwright/lpg_consulta_client.py` | funciones de diagnóstico devuelven bytes |
| `backend/app/workers/playwright_jobs.py` | persistir `JobScreenshot` al fallar |
| `backend/app/services/screenshot_service.py` | `purge_old_screenshots` |
| `backend/worker_scheduler.py` | cablear la purga |
| `backend/app/config.py` | `SCREENSHOT_RETENTION_DAYS` |
| `backend/app/api/jobs.py` | endpoint `/jobs/<id>/screenshot` + `tiene_screenshot` en serializer |
| `frontend/src/api/jobs.ts` | `tiene_screenshot` en `Job` + `downloadJobScreenshot` |
| `frontend/src/components/dashboard/JobDetailDrawer.tsx` | sección de imagen |

---

## Task 1: Modelo `JobScreenshot` + migración

**Files:**
- Create: `backend/app/models/job_screenshot.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/20260623_0017_add_job_screenshot.py`

**Interfaces:**
- Produces: `JobScreenshot` con columnas `id`, `extraction_job_id` (FK, index), `taxpayer_id` (FK), `image_base64` (Text NOT NULL), `fase` (String(40) nullable), `created_at` (DateTime).

- [ ] **Step 1: Crear el modelo**

Crear `backend/app/models/job_screenshot.py`:

```python
from ..extensions import db
from ..time_utils import now_cordoba_naive


class JobScreenshot(db.Model):
    __tablename__ = "job_screenshot"

    id = db.Column(db.Integer, primary_key=True)
    extraction_job_id = db.Column(
        db.Integer,
        db.ForeignKey("extraction_job.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    taxpayer_id = db.Column(db.Integer, db.ForeignKey("taxpayer.id"), nullable=True)
    image_base64 = db.Column(db.Text, nullable=False)
    fase = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive)
```

- [ ] **Step 2: Exportar en `models/__init__.py`**

Mirar cómo se exportan los otros modelos en `backend/app/models/__init__.py` (ej. `from .pdf_cache import PdfCache`) y agregar la línea análoga:
```python
from .job_screenshot import JobScreenshot
```
Si hay un `__all__`, agregar `"JobScreenshot"`.

- [ ] **Step 3: Crear la migración**

> Confirmar head con: `cd backend && python3 -c "import glob,re; [print(re.search(r'revision\s*=\s*[\"\x27]([^\"\x27]+)', open(f).read()).group(1)) for f in glob.glob('migrations/versions/*.py')]" | sort | tail` — esperado `20260623_0016`.

Crear `backend/migrations/versions/20260623_0017_add_job_screenshot.py`:

```python
"""Add job_screenshot table.

Persiste el screenshot de fallo del robot (base64) asociado a un extraction_job,
para mostrarlo en la UI. Tabla aparte para no inflar extraction_job con blobs.

Revision ID: 20260623_0017
Revises: 20260623_0016
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "20260623_0017"
down_revision = "20260623_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_screenshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("extraction_job_id", sa.Integer(), nullable=False),
        sa.Column("taxpayer_id", sa.Integer(), nullable=True),
        sa.Column("image_base64", sa.Text(), nullable=False),
        sa.Column("fase", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["extraction_job_id"], ["extraction_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["taxpayer_id"], ["taxpayer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_screenshot_extraction_job_id", "job_screenshot", ["extraction_job_id"]
    )
    op.create_index(
        "ix_job_screenshot_created_at", "job_screenshot", ["created_at"]
    )


def downgrade():
    op.drop_index("ix_job_screenshot_created_at", table_name="job_screenshot")
    op.drop_index("ix_job_screenshot_extraction_job_id", table_name="job_screenshot")
    op.drop_table("job_screenshot")
```

> El índice en `created_at` sirve a la purga (filtra por fecha).

- [ ] **Step 4: Aplicar y verificar**

Run: `docker exec liquidacion_granos-backend-1 flask --app run.py db upgrade`
Then: `docker exec liquidacion_granos-postgres-1 psql -U liquidacion -d liquidacion_granos -c "\d job_screenshot"`
Expected: tabla creada con las columnas e índices.

> Si la migración se cuelga por un SELECT idle-in-transaction, terminar ese backend con `pg_terminate_backend` y reintentar (pasó en migraciones previas de esta sesión).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/job_screenshot.py backend/app/models/__init__.py backend/migrations/versions/20260623_0017_add_job_screenshot.py
git commit -m "feat(extracciones): tabla job_screenshot"
```

---

## Task 2: Cliente Playwright devuelve los bytes del screenshot

**Files:**
- Modify: `backend/app/integrations/playwright/lpg_consulta_client.py`

**Interfaces:**
- Produces: `_log_login_diagnostics(login_page, empresa) -> bytes | None` y `_log_search_service_diagnostics(login_page, visible_services) -> bytes | None` devuelven los bytes PNG capturados (o None si la captura falló). El cliente expone el último screenshot capturado vía atributo `self._last_failure_screenshot: bytes | None`.

> Contexto: ambas funciones de diagnóstico ya capturan con `login_page.screenshot(path=..., full_page=True)` a `/tmp`. Hay que ADEMÁS capturar los bytes en memoria (`screenshot(full_page=True)` sin `path` devuelve `bytes`) y retornarlos. El `__init__` del cliente debe inicializar `self._last_failure_screenshot = None`. Las funciones, al capturar, setean ese atributo y lo retornan.

- [ ] **Step 1: Inicializar el atributo en `__init__`**

En `ArcaLpgPlaywrightClient.__init__`, junto a los otros atributos de estado (ej. `self._current_phase = None`), agregar:
```python
        self._last_failure_screenshot: bytes | None = None
```

- [ ] **Step 2: `_log_login_diagnostics` captura bytes y los retorna**

En `_log_login_diagnostics`, en el bloque donde hace `login_page.screenshot(path=screenshot_path, full_page=True)`, cambiar para capturar también los bytes. Reemplazar el try/except del screenshot por:

```python
        screenshot_bytes: bytes | None = None
        screenshot_path = ""
        try:
            debug_dir = os.getenv("PLAYWRIGHT_DEBUG_PATH", "/tmp/playwright_debug")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = now_cordoba_naive().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(debug_dir, f"login_fail_{timestamp}.png")
            screenshot_bytes = login_page.screenshot(full_page=True)
            with open(screenshot_path, "wb") as fh:
                fh.write(screenshot_bytes)
        except Exception as exc:
            screenshot_path = f"screenshot_failed:{exc.__class__.__name__}"
```

Al final de la función, después del `logger.warning(...)`, agregar:
```python
        self._last_failure_screenshot = screenshot_bytes
        return screenshot_bytes
```
Y cambiar la anotación de retorno de la función a `-> bytes | None`.

- [ ] **Step 3: `_log_search_service_diagnostics` igual**

Aplicar el mismo cambio en `_log_search_service_diagnostics`: capturar `screenshot_bytes = login_page.screenshot(full_page=True)`, escribirlo a disco con `open(...).write`, setear `self._last_failure_screenshot = screenshot_bytes` y `return screenshot_bytes`. Anotación `-> bytes | None`.

> Las llamadas existentes a estas funciones (líneas ~529 y ~838) ignoran el retorno hoy;
> dejarlas como están — el cliente expone los bytes vía `self._last_failure_screenshot`,
> que es lo que el pipeline va a leer. No hace falta cambiar los call sites.

- [ ] **Step 4: Verificar compilación**

Run: `cd backend && python3 -m compileall app/integrations/playwright/lpg_consulta_client.py -q && echo OK`
Expected: `OK`.

- [ ] **Step 5: Correr tests del cliente (no romper)**

Run: `cd backend && python3 -m pytest tests/unit/test_lpg_consulta_client_service_open.py tests/unit/test_playwright_early_step_robustness.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/playwright/lpg_consulta_client.py
git commit -m "feat(playwright): retener bytes del screenshot de fallo"
```

---

## Task 3: Propagar el screenshot por el pipeline

**Files:**
- Modify: `backend/app/services/lpg_playwright_pipeline.py`

**Interfaces:**
- Consumes: `client._last_failure_screenshot` (Task 2).
- Produces: `TaxpayerPipelineResult.failure_screenshot_png: bytes | None = None`, poblado en los handlers de error desde `client._last_failure_screenshot`.

> Contexto: `TaxpayerPipelineResult` es un `@dataclass(slots=True)` (~línea 40) con `failure_phase`, `failure_error_type`, etc. Los handlers de error (~líneas 294-317) ya hacen `base.failure_phase = ...` leyendo del `client`. Agregar la lectura del screenshot ahí.

- [ ] **Step 1: Agregar el campo al dataclass**

En `TaxpayerPipelineResult`, junto a `failure_dropdown_clicked: bool = False`, agregar:
```python
    failure_screenshot_png: bytes | None = None
```

- [ ] **Step 2: Poblarlo en los handlers de error**

En `_process_taxpayer` (o donde estén los handlers `except PlaywrightFlowError` y `except Exception` que setean `base.failure_phase`), agregar en cada uno, después de setear los otros campos de fallo:
```python
            base.failure_screenshot_png = getattr(client, "_last_failure_screenshot", None)
```

> Usar `getattr` con default None por seguridad: el `client` podría no existir si el fallo
> fue antes de instanciarlo (ej. en la validación de config previa). Verificar cada handler:
> si `client` no está definido en ese scope, no agregar la línea ahí (solo donde `client` existe,
> que son los handlers de error Playwright).

- [ ] **Step 3: Verificar compilación**

Run: `cd backend && python3 -m compileall app/services/lpg_playwright_pipeline.py -q && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/lpg_playwright_pipeline.py
git commit -m "feat(extracciones): propagar screenshot de fallo en el pipeline result"
```

---

## Task 4: Persistir `JobScreenshot` en el worker

**Files:**
- Modify: `backend/app/workers/playwright_jobs.py`
- Test: `backend/tests/unit/test_job_screenshot_persist.py`

**Interfaces:**
- Consumes: `result.failure_screenshot_png` (Task 3), `JobScreenshot` (Task 1).
- Produces: tras un job fallido con screenshot, existe un registro `JobScreenshot` con el base64.

> Contexto: en `playwright_jobs.py`, el callback por-taxpayer (`on_taxpayer_finish`, ~línea 425) tiene acceso a `result` (un `TaxpayerPipelineResult`) y al `extraction_job_id`. Ahí se persiste el fallo. Agregar la creación del `JobScreenshot` cuando `result.failure_screenshot_png` no es None. Importar `base64` y `JobScreenshot`.

- [ ] **Step 1: Escribir el test (falla)**

Crear `backend/tests/unit/test_job_screenshot_persist.py`:

```python
import base64
from app.extensions import db
from app.models import ExtractionJob, JobScreenshot
from app.workers.playwright_jobs import _persist_job_screenshot


def test_persist_creates_screenshot(app):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        png = b"\x89PNG\r\n\x1a\nFAKE"
        _persist_job_screenshot(job.id, taxpayer_id=1, png_bytes=png, fase="LOGIN_START")
        shot = JobScreenshot.query.filter_by(extraction_job_id=job.id).first()
        assert shot is not None
        assert base64.b64decode(shot.image_base64) == png
        assert shot.fase == "LOGIN_START"


def test_persist_noop_when_none(app):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        _persist_job_screenshot(job.id, taxpayer_id=1, png_bytes=None, fase=None)
        assert JobScreenshot.query.filter_by(extraction_job_id=job.id).first() is None
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `cd backend && python3 -m pytest tests/unit/test_job_screenshot_persist.py -q`
Expected: FAIL — `_persist_job_screenshot` no existe.

- [ ] **Step 3: Implementar el helper**

En `backend/app/workers/playwright_jobs.py`, agregar el import al inicio:
```python
import base64
from ..models import JobScreenshot
```
(si ya se importan modelos de otra forma, seguir ese patrón).

Agregar el helper (cerca de los otros helpers del módulo):
```python
def _persist_job_screenshot(
    extraction_job_id: int,
    *,
    taxpayer_id: int | None,
    png_bytes: bytes | None,
    fase: str | None,
) -> None:
    """Crea un JobScreenshot (base64) si hay bytes. No-op si png_bytes es None."""
    if not png_bytes:
        return
    shot = JobScreenshot(
        extraction_job_id=extraction_job_id,
        taxpayer_id=taxpayer_id,
        image_base64=base64.b64encode(png_bytes).decode("ascii"),
        fase=fase,
    )
    db.session.add(shot)
    db.session.commit()
```

- [ ] **Step 4: Llamar al helper en el callback de fallo por-taxpayer**

En el callback donde se procesa el resultado de cada taxpayer fallido (`on_taxpayer_finish` / donde `result.outcome != "done"` y se llama `_persist_taxpayer_failure`, ~línea 425-451), agregar después de persistir el fallo:
```python
                _persist_job_screenshot(
                    extraction_job_id,
                    taxpayer_id=result.taxpayer_id,
                    png_bytes=result.failure_screenshot_png,
                    fase=result.failure_phase.value if result.failure_phase else None,
                )
```

> Verificar el nombre real del campo de taxpayer en `result` (puede ser `result.taxpayer_id`
> o `result.taxpayer.id`) mirando el dataclass `TaxpayerPipelineResult`. Usar el correcto.

- [ ] **Step 5: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_job_screenshot_persist.py -q`
Expected: PASS.

- [ ] **Step 6: Compile + suite de workers**

Run: `cd backend && python3 -m compileall app -q && python3 -m pytest tests/unit/test_playwright_jobs_failure_code.py -q`
Expected: OK + PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/workers/playwright_jobs.py backend/tests/unit/test_job_screenshot_persist.py
git commit -m "feat(extracciones): persistir screenshot de fallo en job_screenshot"
```

---

## Task 5: Endpoint `/screenshot` + `tiene_screenshot` en serializer

**Files:**
- Modify: `backend/app/api/jobs.py`
- Test: `backend/tests/unit/test_job_screenshot_endpoint.py`

**Interfaces:**
- Consumes: `JobScreenshot` (Task 1).
- Produces: `GET /api/jobs/<id>/screenshot` → PNG (200) / 404; el serializer de `GET /jobs/<id>` incluye `tiene_screenshot: bool`.

> Contexto: `jobs.py` ya tiene `GET /jobs/<int:job_id>` (~línea 122) y un serializer del job. Importa `require_auth`. Para servir el PNG, importar `io`, `base64`, `send_file` y `JobScreenshot`.

- [ ] **Step 1: Escribir los tests (fallan)**

Crear `backend/tests/unit/test_job_screenshot_endpoint.py`:

```python
import base64
from app.extensions import db
from app.models import ExtractionJob, JobScreenshot


def _mk_job_with_shot(app, with_shot=True):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        if with_shot:
            db.session.add(JobScreenshot(
                extraction_job_id=job.id, taxpayer_id=1,
                image_base64=base64.b64encode(b"\x89PNGFAKE").decode("ascii"),
                fase="LOGIN_START",
            ))
            db.session.commit()
        return job.id


def test_screenshot_requires_auth(app, client):
    jid = _mk_job_with_shot(app)
    res = client.get(f"/api/jobs/{jid}/screenshot")
    assert res.status_code == 401


def test_screenshot_returns_png(app, client, auth_headers):
    jid = _mk_job_with_shot(app)
    res = client.get(f"/api/jobs/{jid}/screenshot", headers=auth_headers)
    assert res.status_code == 200
    assert res.mimetype == "image/png"


def test_screenshot_404_when_absent(app, client, auth_headers):
    jid = _mk_job_with_shot(app, with_shot=False)
    res = client.get(f"/api/jobs/{jid}/screenshot", headers=auth_headers)
    assert res.status_code == 404


def test_job_serializer_has_tiene_screenshot(app, client, auth_headers):
    jid = _mk_job_with_shot(app)
    res = client.get(f"/api/jobs/{jid}", headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["tiene_screenshot"] is True
```

> Verificar el fixture de auth real en `conftest.py` (puede ser `auth_headers`); si difiere, adaptar.

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd backend && python3 -m pytest tests/unit/test_job_screenshot_endpoint.py -q`
Expected: FAIL (404 en la ruta nueva; falta `tiene_screenshot`).

- [ ] **Step 3: Agregar el endpoint**

En `backend/app/api/jobs.py`, agregar imports al inicio si faltan:
```python
import io
import base64
from flask import send_file
from ..models import JobScreenshot
```

Agregar el endpoint (cerca de `get_job`):
```python
@jobs_bp.get("/jobs/<int:job_id>/screenshot")
@require_auth
def get_job_screenshot(job_id: int):
    shot = (
        JobScreenshot.query.filter_by(extraction_job_id=job_id)
        .order_by(JobScreenshot.id.desc())
        .first()
    )
    if shot is None:
        return {"error": "No hay captura para este job."}, 404
    return send_file(
        io.BytesIO(base64.b64decode(shot.image_base64)),
        mimetype="image/png",
    )
```

- [ ] **Step 4: Agregar `tiene_screenshot` al serializer del job**

Ubicar la función que serializa un `ExtractionJob` a dict (la usa `GET /jobs/<id>`). Agregar la clave:
```python
        "tiene_screenshot": JobScreenshot.query.filter_by(
            extraction_job_id=job.id
        ).first() is not None,
```

> Si el serializer se usa también en la lista paginada de jobs y agregar este query por fila
> introduce N+1, limitarlo SOLO al serializer del detalle (`get_job`). Verificar dónde se usa
> el serializer; si es compartido, computar `tiene_screenshot` solo en `get_job` y no en la lista.

- [ ] **Step 5: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_job_screenshot_endpoint.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/jobs.py backend/tests/unit/test_job_screenshot_endpoint.py
git commit -m "feat(extracciones): endpoint y flag de screenshot del job"
```

---

## Task 6: Purga automática de screenshots viejos

**Files:**
- Create: `backend/app/services/screenshot_service.py`
- Modify: `backend/app/config.py`, `backend/worker_scheduler.py`
- Test: `backend/tests/unit/test_screenshot_purge.py`

**Interfaces:**
- Consumes: `JobScreenshot` (Task 1).
- Produces: `purge_old_screenshots(max_age_days: int) -> int` (cantidad borrada). `Config.SCREENSHOT_RETENTION_DAYS`.

- [ ] **Step 1: Escribir el test (falla)**

Crear `backend/tests/unit/test_screenshot_purge.py`:

```python
import base64
from datetime import timedelta
from app.extensions import db
from app.models import ExtractionJob, JobScreenshot
from app.time_utils import now_cordoba_naive
from app.services.screenshot_service import purge_old_screenshots


def _mk_shot(app, days_ago):
    with app.app_context():
        job = ExtractionJob(taxpayer_id=1, operation="scheduler_lpg_extract", status="failed")
        db.session.add(job)
        db.session.commit()
        shot = JobScreenshot(
            extraction_job_id=job.id, taxpayer_id=1,
            image_base64=base64.b64encode(b"X").decode("ascii"),
            created_at=now_cordoba_naive() - timedelta(days=days_ago),
        )
        db.session.add(shot)
        db.session.commit()
        return shot.id


def test_purge_deletes_old_keeps_recent(app):
    old_id = _mk_shot(app, days_ago=5)
    recent_id = _mk_shot(app, days_ago=1)
    with app.app_context():
        n = purge_old_screenshots(max_age_days=3)
        assert n == 1
        assert JobScreenshot.query.get(old_id) is None
        assert JobScreenshot.query.get(recent_id) is not None
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `cd backend && python3 -m pytest tests/unit/test_screenshot_purge.py -q`
Expected: FAIL — módulo no existe.

- [ ] **Step 3: Implementar el servicio**

Crear `backend/app/services/screenshot_service.py`:

```python
from __future__ import annotations

import logging
from datetime import timedelta

from ..extensions import db
from ..models import JobScreenshot
from ..time_utils import now_cordoba_naive

logger = logging.getLogger(__name__)


def purge_old_screenshots(max_age_days: int) -> int:
    """Borra los JobScreenshot con created_at más viejo que max_age_days.
    Devuelve la cantidad borrada.
    """
    cutoff = now_cordoba_naive() - timedelta(days=max_age_days)
    deleted = (
        JobScreenshot.query.filter(JobScreenshot.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    if deleted:
        db.session.commit()
        logger.info("SCREENSHOT_PURGE | borrados=%s cutoff=%s", deleted, cutoff)
    return deleted
```

- [ ] **Step 4: Agregar la config**

En `backend/app/config.py`, junto a las otras settings, agregar:
```python
    SCREENSHOT_RETENTION_DAYS = int(os.getenv("SCREENSHOT_RETENTION_DAYS", "3"))
```
(seguir el patrón de cómo se leen las otras env vars en config.py — `os.getenv` ya debería estar importado).

- [ ] **Step 5: Cablear la purga en el loop del scheduler**

En `backend/worker_scheduler.py`, en el `import` agregar `purge_old_screenshots` y en el loop `while True` (después del bloque de `reconcile_stale_jobs`, antes de `time.sleep`):

```python
            try:
                from flask import current_app
                # ponytail: corre cada tick; el DELETE por fecha es barato (índice en created_at) e idempotente
                purge_old_screenshots(current_app.config["SCREENSHOT_RETENTION_DAYS"])
            except Exception:
                logger.exception("purge_old_screenshots falló")
```

Y el import al inicio:
```python
from app.services.screenshot_service import purge_old_screenshots
```

- [ ] **Step 6: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_screenshot_purge.py -q && cd backend && python3 -m compileall app worker_scheduler.py -q && echo OK`
Expected: PASS + OK.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/screenshot_service.py backend/app/config.py backend/worker_scheduler.py backend/tests/unit/test_screenshot_purge.py
git commit -m "feat(extracciones): purga automática de screenshots viejos"
```

---

## Task 7: Frontend — mostrar el screenshot en el drawer

**Files:**
- Modify: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/components/dashboard/JobDetailDrawer.tsx`

**Interfaces:**
- Consumes: endpoint `/jobs/<id>/screenshot` y `tiene_screenshot` (Task 5).
- Produces: el drawer muestra la imagen cuando `job.tiene_screenshot`.

- [ ] **Step 1: Agregar `tiene_screenshot` al tipo y la función de descarga**

En `frontend/src/api/jobs.ts`:
- En la interfaz `Job`, agregar:
```typescript
  tiene_screenshot: boolean;
```
- Agregar la función (patrón de `downloadCoePdf`):
```typescript
export async function downloadJobScreenshot(id: number): Promise<Blob> {
  const res = await fetchWithAuth(`/jobs/${id}/screenshot`, { method: "GET" });
  if (!res.ok) {
    throw new Error("No se pudo obtener la captura.");
  }
  return res.blob();
}
```

- [ ] **Step 2: Type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: puede fallar si algún mock de `Job` en tests no tiene `tiene_screenshot` — si TS se queja en archivos de test, agregar `tiene_screenshot: false` a esos mocks. En código de producción no debería romper (la prop viene del backend).

- [ ] **Step 3: Mostrar la imagen en el drawer**

En `frontend/src/components/dashboard/JobDetailDrawer.tsx`:
- Importar: `import { useState, useEffect } from "react";` (si no están) y `import { downloadJobScreenshot } from "../../api/jobs";`
- Dentro del componente, agregar carga del objectURL cuando hay screenshot:
```typescript
  const [shotUrl, setShotUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!job?.tiene_screenshot) {
      setShotUrl(null);
      return;
    }
    let revoked = false;
    let url: string | null = null;
    downloadJobScreenshot(job.id)
      .then((blob) => {
        if (revoked) return;
        url = URL.createObjectURL(blob);
        setShotUrl(url);
      })
      .catch(() => setShotUrl(null));
    return () => {
      revoked = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [job?.id, job?.tiene_screenshot]);
```
- En el JSX, después de la sección "Detalle técnico" (dentro del bloque de `job.status === "failed"` o donde tenga sentido visualmente), agregar:
```tsx
          {job.tiene_screenshot ? (
            <section className="mt-3">
              <h3 className="text-sm font-semibold text-slate-700 mb-2">
                Captura de pantalla
              </h3>
              {shotUrl ? (
                <img
                  src={shotUrl}
                  alt="Captura del momento del fallo"
                  className="w-full rounded-md border border-slate-200"
                />
              ) : (
                <p className="text-sm text-slate-500">Cargando captura…</p>
              )}
            </section>
          ) : null}
```

> Ubicar el lugar exacto leyendo el JSX real del drawer; el `job` ahí es de tipo `Job`.
> Asegurar que la sección quede dentro del render donde `job` no es null.

- [ ] **Step 4: Type check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: ambos OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/jobs.ts frontend/src/components/dashboard/JobDetailDrawer.tsx
git commit -m "feat(extracciones): mostrar captura de pantalla del fallo en el drawer"
```

---

## Task 8: Verificación integral y PR

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && python3 -m pytest tests/ -q`
Expected: todo verde.

- [ ] **Step 2: Compile + frontend**

Run: `cd backend && python3 -m compileall app -q && echo OK && cd ../frontend && npx tsc --noEmit && npm run build`
Expected: OK + ambos frontend OK.

- [ ] **Step 3: Fresh-context code review del diff contra dev.**

- [ ] **Step 4: Push y PR a dev**

```bash
git push -u origin feature/080-screenshot-fallo-visible
gh pr create --base dev --head feature/080-screenshot-fallo-visible \
  --title "feat(extracciones): screenshot de fallo visible en el panel" \
  --body "Persiste el screenshot que el robot captura al fallar y lo muestra en el JobDetailDrawer, con purga automática tras N días. Closes spec 2026-06-23-screenshot-fallo-visible-design."
```
Expected: PR creado, CI en verde.

---

## Self-Review

**Spec coverage:**
- Tabla `job_screenshot` (base64, patrón pdf_cache) → Task 1. ✅
- Propagación cliente→worker vía `TaxpayerPipelineResult.failure_screenshot_png` → Tasks 2, 3. ✅
- Persistir JobScreenshot al fallar → Task 4. ✅
- Endpoint `/screenshot` con auth + `tiene_screenshot` en serializer → Task 5. ✅
- Frontend: imagen en el drawer cargada como blob (patrón PDF, no `<img src>` plano) → Task 7. ✅
- Purga cada N días (default 3), configurable, cableada en el scheduler loop → Task 6. ✅
- Tests backend de todos los puntos → Tasks 4, 5, 6. ✅

**Placeholder scan:** sin TBD/TODO; cada step de código muestra el código. Las notas
"verificar nombre real del campo" / "ubicar por contenido" son por números de línea
aproximados en archivos grandes, no placeholders de lógica.

**Type consistency:**
- `failure_screenshot_png: bytes | None` consistente: dataclass (Task 3), lectura en worker (Task 4).
- `_persist_job_screenshot(extraction_job_id, *, taxpayer_id, png_bytes, fase)` consistente entre Task 4 (def) y sus tests.
- `purge_old_screenshots(max_age_days: int) -> int` consistente entre Task 6 (def), test y cableado.
- `tiene_screenshot: bool` (backend serializer Task 5) ↔ `tiene_screenshot: boolean` (TS Task 7).
- `downloadJobScreenshot(id) -> Promise<Blob>` consistente entre Task 7 (def) y su uso en el drawer.
- `JobScreenshot` columnas (`extraction_job_id`, `image_base64`, `fase`, `created_at`) consistentes entre modelo (Task 1), persistencia (Task 4), endpoint (Task 5) y purga (Task 6).
