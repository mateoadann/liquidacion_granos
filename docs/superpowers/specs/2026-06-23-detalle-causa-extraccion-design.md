# Feature 077 — Detalle de causa de extracción

**Fecha:** 2026-06-23
**Rama:** `feature/077-detalle-causa-extraccion` (desde `dev`)
**Estado:** Diseño aprobado

## Problema

En el panel `/extracciones/salud` (feature 076), cuando un cliente está caído con una
causa vaga (ej. Erlina S.A.S., 13 días sin éxito, mensaje *"Ocurrió un problema al
consultar Arca. Reintentará automáticamente."*), el usuario **no tiene forma de saber
qué pasó en realidad** ni qué hacer al respecto.

Dos causas verificadas sobre la DB de producción:

1. **El detalle existe pero no se muestra.** El último job de Erlina tiene en
   `failure_message_technical`: *"Locator.fill: Timeout esperando el campo TU CLAVE"* —
   o sea, se colgó en el login esperando el campo de clave fiscal. El panel no expone
   ese detalle.
2. **El mensaje cae al genérico cuando falta la fase.** `map_failure` decide el mensaje
   a partir de `(phase, error_type)`. Cuando `phase` es null y `error_type` es
   `timeout`/`unknown`, devuelve el mensaje genérico — aunque el texto técnico tenga la
   pista de dónde se colgó. En la data histórica, ~65% de los fallos no tienen fase.

## Alcance (feature 077)

Dos piezas, ambas apoyándose en código existente:

1. **Drawer de detalle** al hacer clic en cualquier fila del panel — reusa el
   `JobDetailDrawer` y `useJobQuery` que ya existen.
2. **Inferencia de causa desde el técnico** — una función nueva que, cuando no hay fase,
   la infiere del `failure_message_technical` para producir un mensaje accionable mejor.
   Aplica **solo a fallos nuevos** (sin backfill de históricos).

Fuera de alcance: historial de intentos por cliente, reintento manual desde el panel
(el `JobDetailDrawer` ya trae su propio botón "Reintentar" para jobs elegibles, así que
viene gratis del reuso, pero no se diseña nada nuevo alrededor).

## Código existente que se reusa (no se reconstruye)

- `GET /api/jobs/<int:job_id>` — endpoint que devuelve un `ExtractionJob` completo.
- `useJobQuery(id)` (`frontend/src/hooks/useJobs.ts`) — hook TanStack Query.
- `JobDetailDrawer` (`frontend/src/components/dashboard/JobDetailDrawer.tsx`) — drawer
  que ya muestra: información general, causa del error (`failure_message_user`), fase,
  **detalle técnico plegable** (`<details>` con `failure_message_technical`) y botón
  "Reintentar" para jobs elegibles. Recibe un objeto `Job`.

## Pieza 1 — Drawer de detalle en el panel

### Backend
`compute_health()` agrega `last_job_id` a cada cliente: el `id` del último job (que ya
se consulta en el servicio para obtener `last_status`/`failure_code`; hoy se descarta el
`id`). `null` solo si el cliente no tiene jobs.

### Frontend
- `ClienteSalud` suma `last_job_id: number | null`.
- Todas las filas de la tabla son clickeables (`TableRow` ya acepta `onClick`), incluidas
  las verdes — ver el detalle de una extracción exitosa (COEs traídos, fechas) también es
  útil; el `JobDetailDrawer` ya maneja status `completed`.
- Al hacer clic en una fila con `last_job_id`: `useJobQuery(last_job_id)` trae el job
  completo y se pasa a `JobDetailDrawer`. Filas sin `last_job_id` (cliente sin jobs) no
  abren drawer.
- Estado local: `selectedJobId: number | null` (mismo patrón que `ExtractionsListPage`).

## Pieza 2 — Inferencia de causa desde el técnico

### Función nueva
En `extraction_failure_mapper.py`:

```python
def infer_phase_from_technical(tech: str | None) -> ExtractionPhase | None
```

Busca marcadores conocidos (case-insensitive) en el texto técnico y devuelve la fase
probable, o `None` si no hay marcador reconocible. Marcadores derivados de la data real:

| Marcador en el técnico (regex/substring, case-insensitive) | Fase inferida |
|---|---|
| `TU CLAVE`, `Clave`, `usuario` | `LOGIN_START` |
| `Liquidaci[oó]n Primaria de Granos`, `buscador` | `SEARCH_SERVICE` |
| `Consultar Por Criterio`, `Consulta Liquidaciones Recibidas` | `OPEN_CONSULTA_RECIBIDAS` |
| `Fecha Desde` | `SET_FECHAS` |
| `liquidacionXCoeConsultar` | `SAVING_TO_WS` |

Orden de evaluación: el más específico primero (login antes que genéricos). Si ningún
marcador matchea → `None`.

### Dónde se aplica
En el worker (`playwright_jobs.py`), en los puntos donde hoy se llama `map_failure` con
una `phase` que puede ser `None`. Cuando `phase is None` y hay `exception_text`, se
intenta `infer_phase_from_technical(exception_text)`; si devuelve una fase, se usa esa
para `map_failure(inferred_phase, error_type, ...)`. Si devuelve `None`, el
comportamiento es el actual (mensaje genérico).

Esto mejora `failure_code` y `failure_message_user` del job, y el panel los muestra mejor
automáticamente — sin tocar el frontend de los mensajes.

### Límite explícito
Un timeout genérico de navegación sin marcador reconocible (ej. `"Timeout 30000ms
exceeded"` a secas, sin contexto de campo) seguirá cayendo en `UNKNOWN_ERROR`. La
inferencia recupera los fallos que tienen pista en el técnico, no inventa la que no
está. Aplica solo a fallos nuevos; los ~56 históricos quedan como están.

## Testing

### Backend (pytest, TDD)
- `infer_phase_from_technical`:
  - texto con "TU CLAVE" / "Clave" → `LOGIN_START`
  - texto con "Liquidación Primaria de Granos" → `SEARCH_SERVICE`
  - texto con "Fecha Desde" → `SET_FECHAS`
  - texto con "liquidacionXCoeConsultar" → `SAVING_TO_WS`
  - texto con "Consulta Liquidaciones Recibidas" → `OPEN_CONSULTA_RECIBIDAS`
  - texto sin marcador → `None`
  - `None` / "" → `None`
- Integración en el worker: con `phase=None` y `exception_text` que contiene "TU CLAVE",
  el job persiste un `failure_code` distinto de `UNKNOWN_ERROR` (el correspondiente a
  LOGIN_START), no el genérico.
- `compute_health` incluye `last_job_id` en cada cliente (con valor y con `None` para
  cliente sin jobs).

### Frontend
`cd frontend && npx tsc --noEmit` + `npm run build`. Fila clickeable + drawer se validan
visualmente (no hay runner de tests de UI).

## Archivos afectados (estimado)

- `backend/app/services/extraction_failure_mapper.py` — `infer_phase_from_technical`
- `backend/app/workers/playwright_jobs.py` — inferencia como fallback cuando `phase is None`
- `backend/app/services/extraction_health.py` — `last_job_id` en cada cliente
- `backend/tests/unit/test_extraction_failure_mapper.py` — tests de inferencia
- `backend/tests/unit/test_extraction_health.py` — test de `last_job_id`
- `frontend/src/api/extracciones.ts` — `last_job_id` en `ClienteSalud`
- `frontend/src/pages/ExtractionHealthPage.tsx` — fila clickeable + `useJobQuery` + `JobDetailDrawer`

## Fuera de alcance (features futuras)

- Historial de los últimos N intentos por cliente.
- Backfill de inferencia sobre fallos históricos.
- Traducción del técnico crudo a explicación legible adicional (el drawer ya muestra
  `failure_message_user` legible arriba + el técnico crudo plegable; alcanza para este
  alcance).
