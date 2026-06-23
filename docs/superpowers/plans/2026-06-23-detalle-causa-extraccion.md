# Detalle de causa de extracción (077) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el usuario pueda entender qué pasó con un cliente caído en `/extracciones/salud`: ver el detalle del último job (reusando el drawer existente) y obtener mensajes más accionables inferidos del texto técnico cuando falta la fase.

**Architecture:** Dos piezas. (1) El endpoint de salud expone `last_job_id`; el panel hace cada fila clickeable y reusa `JobDetailDrawer` + `useJobQuery` (ya existentes) para mostrar el detalle. (2) Una función nueva `infer_phase_from_technical` infiere la fase desde `failure_message_technical` cuando el flujo no la determinó, y el worker la usa como fallback antes de `map_failure`, mejorando `failure_code`/`failure_message_user` de los fallos nuevos.

**Tech Stack:** Flask + SQLAlchemy (backend), pytest, React 18 + TypeScript + TanStack Query (frontend).

## Global Constraints

- Timestamps timezone America/Argentina/Cordoba (`now_cordoba_naive()` de `app/time_utils.py`).
- Endpoints protegidos con `@require_auth` (de `app.middleware`).
- `from __future__ import annotations` en módulos tipados nuevos.
- Payloads backend `snake_case`; tipos frontend con TypeScript estricto, no debilitar.
- 2-space indent, double quotes, semicolons (frontend).
- **Fechas en la UI: SIEMPRE formato DD/MM/AAAA** — usar `formatDateOnly`/`formatDateTime` de `frontend/src/dateUtils.ts` (el `JobDetailDrawer` ya las usa).
- Mensajes al usuario: "Arca" (no "ARCA"/"AFIP"); sin jerga técnica (playwright/scheduler/worker) en `failure_message_user`.
- Solo fallos nuevos: la inferencia corre en el worker al fallar; sin backfill de históricos.
- Comandos de test: backend `cd backend && python3 -m pytest <ruta> -q` (el binario es `python3`, no `python`); frontend `cd frontend && npx tsc --noEmit` y `npm run build`.
- Fases conocidas (`ExtractionPhase` en `app/services/extraction_phases.py`): LAUNCHING_BROWSER, LOGIN_START, LOGIN_CONFIRMED, SEARCH_SERVICE, OPEN_SERVICE, SELECT_EMPRESA, OPEN_CONSULTA_RECIBIDAS, SET_FECHAS, LISTING_COES, DOWNLOADING_COE, SAVING_TO_WS, FINISHED.

---

## File Structure

| Archivo | Responsabilidad |
|---------|-----------------|
| `backend/app/services/extraction_failure_mapper.py` | nueva `infer_phase_from_technical(tech)` |
| `backend/app/workers/playwright_jobs.py` | usar inferencia como fallback cuando `phase is None` (2 puntos) |
| `backend/app/services/extraction_health.py` | agregar `last_job_id` a cada cliente |
| `backend/tests/unit/test_extraction_failure_mapper.py` | tests de inferencia |
| `backend/tests/unit/test_extraction_health.py` | test de `last_job_id` |
| `frontend/src/api/extracciones.ts` | `last_job_id` en `ClienteSalud` |
| `frontend/src/pages/ExtractionHealthPage.tsx` | fila clickeable + `useJobQuery` + `JobDetailDrawer` |

Reuso sin tocar: `GET /api/jobs/<id>`, `useJobQuery` (`hooks/useJobs.ts`), `JobDetailDrawer` (`components/dashboard/JobDetailDrawer.tsx`).

---

## Task 1: `infer_phase_from_technical`

**Files:**
- Modify: `backend/app/services/extraction_failure_mapper.py`
- Test: `backend/tests/unit/test_extraction_failure_mapper.py`

**Interfaces:**
- Produces: `infer_phase_from_technical(tech: str | None) -> ExtractionPhase | None` — devuelve la fase probable según marcadores en el texto técnico, o `None` si no hay marcador reconocible o el texto es vacío/None.

- [ ] **Step 1: Escribir los tests que fallan**

En `backend/tests/unit/test_extraction_failure_mapper.py`, agregar:

```python
from app.services.extraction_failure_mapper import infer_phase_from_technical
from app.services.extraction_phases import ExtractionPhase


def test_infer_login_from_tu_clave():
    tech = 'Locator.fill: Timeout 30000ms exceeded. waiting for textbox "TU CLAVE"'
    assert infer_phase_from_technical(tech) == ExtractionPhase.LOGIN_START


def test_infer_login_from_clave_word():
    assert infer_phase_from_technical("waiting for Clave field") == ExtractionPhase.LOGIN_START


def test_infer_search_service():
    tech = 'waiting for button "Liquidación Primaria de Granos"'
    assert infer_phase_from_technical(tech) == ExtractionPhase.SEARCH_SERVICE


def test_infer_set_fechas():
    assert infer_phase_from_technical("No se encontró input de Fecha Desde.") == ExtractionPhase.SET_FECHAS


def test_infer_saving_ws():
    assert infer_phase_from_technical("Error en liquidacionXCoeConsultar") == ExtractionPhase.SAVING_TO_WS


def test_infer_consulta_recibidas():
    tech = 'waiting for button "Consulta Liquidaciones Recibidas"'
    assert infer_phase_from_technical(tech) == ExtractionPhase.OPEN_CONSULTA_RECIBIDAS


def test_infer_none_when_no_marker():
    assert infer_phase_from_technical("Timeout 30000ms exceeded") is None


def test_infer_none_for_empty():
    assert infer_phase_from_technical(None) is None
    assert infer_phase_from_technical("") is None
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_failure_mapper.py -k infer -q`
Expected: FAIL — `ImportError: cannot import name 'infer_phase_from_technical'`.

- [ ] **Step 3: Implementar la función**

En `backend/app/services/extraction_failure_mapper.py`, agregar al final del archivo (después de `map_failure`):

```python
# Marcadores (substring, case-insensitive) → fase probable. Orden: más específico
# primero. Derivados de los textos técnicos reales de Playwright/ARCA en producción.
_PHASE_MARKERS: list[tuple[tuple[str, ...], ExtractionPhase]] = [
    (("tu clave", "clave", "usuario"), ExtractionPhase.LOGIN_START),
    (("liquidación primaria de granos", "liquidacion primaria de granos", "buscador"),
     ExtractionPhase.SEARCH_SERVICE),
    (("consulta liquidaciones recibidas", "consultar por criterio"),
     ExtractionPhase.OPEN_CONSULTA_RECIBIDAS),
    (("fecha desde",), ExtractionPhase.SET_FECHAS),
    (("liquidacionxcoeconsultar",), ExtractionPhase.SAVING_TO_WS),
]


def infer_phase_from_technical(tech: str | None) -> ExtractionPhase | None:
    """Infiere la fase probable de un fallo a partir del texto técnico crudo.

    Se usa como fallback cuando el flujo no determinó la fase. Devuelve None si el
    texto es vacío/None o no contiene ningún marcador reconocible (NO inventa).
    """
    if not tech:
        return None
    low = tech.lower()
    for markers, phase in _PHASE_MARKERS:
        if any(m in low for m in markers):
            return phase
    return None
```

- [ ] **Step 4: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_failure_mapper.py -k infer -q`
Expected: PASS (los 8 tests de inferencia).

- [ ] **Step 5: Correr todo el archivo (no romper lo existente)**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_failure_mapper.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/extraction_failure_mapper.py backend/tests/unit/test_extraction_failure_mapper.py
git commit -m "feat(extracciones): inferir fase del fallo desde el texto técnico"
```

---

## Task 2: Usar la inferencia en el worker como fallback

**Files:**
- Modify: `backend/app/workers/playwright_jobs.py`

**Interfaces:**
- Consumes: `infer_phase_from_technical` (Task 1), `map_failure` (3-tupla, ya existente).
- Produces: jobs nuevos `failed` cuya fase era `None` pero cuyo técnico tiene pista, ahora persisten un `failure_code`/`failure_message_user` específico en vez del genérico.

> Contexto: hay dos puntos donde se llama `map_failure` con una fase que puede ser `None`:
> (a) `_persist_taxpayer_failure` (~línea 163): `user_es, tech_en, code = map_failure(phase, error_type, dropdown_clicked)`, y la función recibe `exception_text` como parámetro.
> (b) el handler `except Exception as exc` (~línea 572): `user_es, tech_en, code = map_failure(None, "unknown", False)`, con `exc` disponible.
> Los números de línea son aproximados; ubicá por contenido. Importá `infer_phase_from_technical` junto a `map_failure` y `_truncate` (línea ~10).

- [ ] **Step 1: Escribir el test de integración (falla)**

Crear `backend/tests/unit/test_worker_phase_inference.py`:

```python
from app.services.extraction_failure_mapper import map_failure, infer_phase_from_technical
from app.services.extraction_phases import ExtractionPhase


def test_inference_changes_unknown_to_specific_code():
    # Sin fase + técnico genérico → UNKNOWN_ERROR (comportamiento actual)
    _, _, code_generic = map_failure(None, "timeout")
    assert code_generic == "UNKNOWN_ERROR"

    # Con técnico que tiene pista de login, la fase inferida cambia el código
    tech = 'Locator.fill: Timeout waiting for textbox "TU CLAVE"'
    inferred = infer_phase_from_technical(tech)
    assert inferred == ExtractionPhase.LOGIN_START
    _, _, code_inferred = map_failure(inferred, "timeout")
    assert code_inferred != "UNKNOWN_ERROR"
    assert code_inferred == "TRANSIENT_LOGIN"
```

Este test fija el contrato que el worker explota: inferir la fase ANTES de `map_failure` produce un código mejor. (La integración real en el worker se cubre con este contrato + los tests existentes del worker que siguen verdes.)

- [ ] **Step 2: Correr el test**

Run: `cd backend && python3 -m pytest tests/unit/test_worker_phase_inference.py -q`
Expected: PASS (Task 1 ya lo garantiza). Sirve de guardrail del contrato.

- [ ] **Step 3: Importar la función en el worker**

En `backend/app/workers/playwright_jobs.py`, en el import existente (~línea 10):

Cambiar:
```python
from ..services.extraction_failure_mapper import _truncate, map_failure
```
por:
```python
from ..services.extraction_failure_mapper import (
    _truncate,
    infer_phase_from_technical,
    map_failure,
)
```

- [ ] **Step 4: Aplicar inferencia en `_persist_taxpayer_failure`**

En `_persist_taxpayer_failure` (~línea 163), reemplazar:
```python
    user_es, tech_en, code = map_failure(phase, error_type, dropdown_clicked)
```
por:
```python
    effective_phase = phase
    if effective_phase is None and exception_text:
        effective_phase = infer_phase_from_technical(exception_text)
    user_es, tech_en, code = map_failure(effective_phase, error_type, dropdown_clicked)
```

> Importante: NO cambiar `phase_value = phase.value if phase else None` más abajo en esa
> función — `failure_phase` persiste la fase REAL (None si no se determinó), no la
> inferida. La inferencia solo mejora el mensaje/código, no falsea la fase registrada.
> (Si se quisiera persistir la inferida, sería otra decisión; el spec solo pide mejorar
> el mensaje.)

- [ ] **Step 5: Aplicar inferencia en el handler `except` general**

En el `except Exception as exc:` (~línea 572), reemplazar:
```python
            user_es, tech_en, code = map_failure(None, "unknown", False)
            tech_combined = _truncate(f"{tech_en} | {exc}")
```
por:
```python
            inferred_phase = infer_phase_from_technical(str(exc))
            user_es, tech_en, code = map_failure(inferred_phase, "unknown", False)
            tech_combined = _truncate(f"{tech_en} | {exc}")
```

- [ ] **Step 6: Verificar compilación**

Run: `cd backend && python3 -m compileall app -q && echo OK`
Expected: `OK`.

- [ ] **Step 7: Correr suites del worker y mapper (no romper nada)**

Run: `cd backend && python3 -m pytest tests/unit/test_worker_phase_inference.py tests/unit/test_playwright_jobs_failure_code.py tests/unit/test_playwright_early_step_robustness.py tests/unit/test_extraction_failure_mapper.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/workers/playwright_jobs.py backend/tests/unit/test_worker_phase_inference.py
git commit -m "feat(extracciones): usar inferencia de fase como fallback al persistir fallos"
```

---

## Task 3: `last_job_id` en el endpoint de salud

**Files:**
- Modify: `backend/app/services/extraction_health.py`
- Test: `backend/tests/unit/test_extraction_health.py`

**Interfaces:**
- Produces: cada cliente del resultado de `compute_health()` incluye `last_job_id: int | None` (el `id` del último job por `created_at`, o `None` si no tiene jobs).

> Contexto: en `compute_health()` ya se consulta `last_job` (`ExtractionJob.query.filter(...).order_by(created_at.desc()).first()`). Solo hay que exponer su `id`.

- [ ] **Step 1: Escribir el test (falla)**

En `backend/tests/unit/test_extraction_health.py`, agregar:

```python
def test_compute_health_includes_last_job_id(app):
    tid = _mk_taxpayer(app, "Cliente ConJob")
    _mk_job(app, tid, "completed", days_ago=0)
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["last_job_id"] is not None
    assert isinstance(row["last_job_id"], int)


def test_compute_health_last_job_id_none_without_jobs(app):
    tid = _mk_taxpayer(app, "Cliente SinJob")
    with app.app_context():
        out = compute_health()
    row = next(c for c in out["clientes"] if c["taxpayer_id"] == tid)
    assert row["last_job_id"] is None
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_health.py -k last_job_id -q`
Expected: FAIL — `KeyError: 'last_job_id'`.

- [ ] **Step 3: Agregar `last_job_id` al dict del cliente**

En `backend/app/services/extraction_health.py`, dentro del `clientes.append({...})`, agregar la clave (junto a `taxpayer_id`):

```python
                "taxpayer_id": t.id,
                "last_job_id": last_job.id if last_job else None,
                "empresa": t.empresa,
```

- [ ] **Step 4: Correr los tests**

Run: `cd backend && python3 -m pytest tests/unit/test_extraction_health.py -q`
Expected: PASS (todos, incluidos los 2 nuevos).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/extraction_health.py backend/tests/unit/test_extraction_health.py
git commit -m "feat(extracciones): exponer last_job_id en el panel de salud"
```

---

## Task 4: Fila clickeable + drawer en el panel

**Files:**
- Modify: `frontend/src/api/extracciones.ts`
- Modify: `frontend/src/pages/ExtractionHealthPage.tsx`

**Interfaces:**
- Consumes: `last_job_id` (Task 3), `useJobQuery(id)` (`hooks/useJobs.ts`, ya existe), `JobDetailDrawer` (`components/dashboard/JobDetailDrawer.tsx`, ya existe — recibe `{ job: Job | null, onClose: () => void }`).

> Contexto: `useJobQuery(id: number | null)` devuelve `{ data: Job | undefined, ... }` y está `enabled` solo si `id !== null`. `JobDetailDrawer` se abre cuando `job !== null`. Patrón de referencia: `ExtractionsListPage` usa `const [selectedJobId, setSelectedJobId] = useState<number | null>(null)`.

- [ ] **Step 1: Agregar `last_job_id` al tipo `ClienteSalud`**

En `frontend/src/api/extracciones.ts`, en la interfaz `ClienteSalud`, agregar tras `taxpayer_id`:

```typescript
  taxpayer_id: number;
  last_job_id: number | null;
  empresa: string | null;
```

- [ ] **Step 2: Type check (debe pasar — solo se agregó un campo opcional de lectura)**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Cablear el drawer en la página**

En `frontend/src/pages/ExtractionHealthPage.tsx`:

3a. Agregar imports (junto a los existentes):
```typescript
import { useState } from "react";
import { useJobQuery } from "../hooks/useJobs";
import { JobDetailDrawer } from "../components/dashboard/JobDetailDrawer";
```

3b. Dentro del componente, al inicio (junto a `const { data, ... } = useExtractionHealthQuery();`):
```typescript
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const selectedJobQuery = useJobQuery(selectedJobId);
```

3c. Hacer cada fila clickeable — en el `<TableRow key={c.taxpayer_id}>`, agregar `onClick` solo si hay `last_job_id`:
```typescript
                  <TableRow
                    key={c.taxpayer_id}
                    onClick={
                      c.last_job_id !== null
                        ? () => setSelectedJobId(c.last_job_id)
                        : undefined
                    }
                  >
```

3d. Antes del cierre del componente (después de `</div>` del contenedor, antes del último `</div>` o donde corresponda según la estructura — ubicar el return raíz), renderizar el drawer:
```typescript
      <JobDetailDrawer
        job={selectedJobQuery.data ?? null}
        onClose={() => setSelectedJobId(null)}
      />
```

> Nota: el drawer recibe el job traído por `useJobQuery`. Mientras carga,
> `selectedJobQuery.data` es `undefined` → se pasa `null` → drawer cerrado; cuando llega
> el job, se abre. Esto produce un pequeño retardo entre el clic y la apertura (1 fetch);
> es aceptable para este alcance. `TableRow` ya aplica `cursor-pointer` cuando hay
> `onClick` (visto en el componente Table).

- [ ] **Step 4: Type check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: ambos OK.

- [ ] **Step 5: Verificación visual**

Con el stack arriba (`make up`), login en `http://localhost:5173`, navegar a "Extracciones". Hacer clic en una fila → se abre el `JobDetailDrawer` mostrando la causa del error, la fase, el detalle técnico plegable y (si aplica) el botón Reintentar. Hacer clic en una fila verde → muestra el detalle del job exitoso.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/extracciones.ts frontend/src/pages/ExtractionHealthPage.tsx
git commit -m "feat(extracciones): abrir detalle del job al hacer clic en una fila del panel"
```

---

## Task 5: Verificación integral y PR

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && python3 -m pytest tests/ -q`
Expected: todo verde.

- [ ] **Step 2: Compile check backend**

Run: `cd backend && python3 -m compileall app -q && echo OK`
Expected: `OK`.

- [ ] **Step 3: Frontend type check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: ambos OK.

- [ ] **Step 4: Fresh-context code review del diff de la rama contra dev.**

- [ ] **Step 5: Push y PR a dev**

```bash
git push -u origin feature/077-detalle-causa-extraccion
gh pr create --base dev --head feature/077-detalle-causa-extraccion \
  --title "feat(extracciones): detalle de causa de extracción" \
  --body "Implementa el drawer de detalle por fila en el panel de salud y la inferencia de causa desde el texto técnico. Closes spec 2026-06-23-detalle-causa-extraccion-design."
```
Expected: PR creado, CI en verde.

---

## Self-Review

**Spec coverage:**
- `infer_phase_from_technical` con marcadores → Task 1. ✅
- Aplicar inferencia como fallback en el worker (2 puntos: `_persist_taxpayer_failure` + except general) → Task 2. ✅
- Solo fallos nuevos, sin backfill → implícito: la inferencia corre en el worker, ningún task toca datos históricos. ✅
- Límite (timeout genérico sin pista → UNKNOWN) → cubierto por `test_infer_none_when_no_marker` (Task 1) y `test_inference...` que parte de UNKNOWN (Task 2). ✅
- `last_job_id` en el endpoint → Task 3. ✅
- Fila clickeable + reuso de `JobDetailDrawer` + `useJobQuery` → Task 4. ✅
- Filas verdes también clickeables → Task 4 Step 3c (onClick si hay last_job_id, sin filtrar por estado). ✅
- Testing backend + frontend tsc/build → Tasks 1-4, 5. ✅

**Placeholder scan:** sin TBD/TODO; cada step de código muestra el código. Los números de línea aproximados en `playwright_jobs.py` están marcados como "ubicá por contenido", no son placeholders de lógica.

**Type consistency:**
- `infer_phase_from_technical(tech: str | None) -> ExtractionPhase | None` consistente entre Task 1 (def), Task 2 (uso en worker) y los tests.
- `last_job_id: int | None` (backend, Task 3) ↔ `last_job_id: number | null` (TS, Task 4) consistente.
- `JobDetailDrawer` props `{ job: Job | null, onClose }` y `useJobQuery(id: number | null)` usados con los tipos correctos en Task 4.
- `selectedJobId: number | null` consistente con el patrón de `ExtractionsListPage`.
