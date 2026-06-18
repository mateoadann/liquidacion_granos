# Diseño: Dashboard mensual + 4 fixes de producción

Fecha: 2026-06-18
Rama: `feature/074-coes-fix-tipo-cte-and-inactive-clients` (se evaluará split de PRs al cerrar)

## Contexto

Cinco objetivos sobre la instancia de producción, testeados con datos reales restaurados
en la DB local (70 taxpayers, 1448 lpg_document, 1556 extraction_job). Decisiones de diseño
ya alineadas con el usuario. Implementación delegada a sub-agentes en paralelo + revisión fresca.

---

## Objetivo 1 — Dashboard de stats por meses

**Problema:** El dashboard raíz `/` (`HomePage.tsx` → `StatsCards.tsx`, endpoint `GET /stats`)
muestra totales globales sin desglose temporal.

**Decisión:**
- **Navegación:** selector mes/año + flechas ←→ para mes anterior/siguiente.
- **Alcance de cards:** solo las métricas que varían por mes se vuelven mensuales:
  **COEs nuevos** y **extracciones exitosas** del mes seleccionado. Las métricas de
  estado actual (clientes totales, clientes activos) NO se mensualizan — siguen siendo
  el estado de hoy.

**Backend** (`backend/app/api/stats.py`):
- Nuevo endpoint o parámetros de período en `/stats` que acepten `mes` y `anio` y devuelvan,
  para ese período: COEs (lpg_document) cuya fecha cae en el mes, y extracciones
  (extraction_job) con `status="completed"` finalizadas en el mes. Filtrar siempre por
  `Taxpayer.activo` consistente con el resto de la app.
- Las cards de estado actual (clientes) se siguen sirviendo igual (no dependen del período).

**Frontend** (`HomePage.tsx`, `StatsCards.tsx`, `hooks/useStats.ts`, `api/stats.ts`):
- Control de período (mes/año + flechas) sobre las cards mensuales.
- Las cards de estado actual quedan visualmente separadas de las mensuales.

---

## Objetivo 2 — Reconciliar jobs colgados en "running"

**Problema:** No existe limpieza de jobs huérfanos. Un job de prod quedó en `running`.
No hay heartbeat ni timeout (confirmado: `scheduler_service.py`, `worker_scheduler.py`
sin reconciliación).

**Decisión:** solo prevención automática (sin tocar data a mano). El job actual se limpia
solo en el próximo ciclo del reconciliador.

**Implementación** (`backend/app/services/scheduler_service.py` + `worker_scheduler.py`):
- En el loop del `scheduler_worker` (ya tickea cada ~60s), agregar un paso de reconciliación
  que marque como `failed` todo `ExtractionJob` con `status="running"` cuyo `updated_at`
  no se actualiza hace más de un umbral (`STALE_JOB_TIMEOUT`, default 30 min).
- Al cerrar: setear `finished_at`, `failure_message_user` ("Proceso interrumpido / sin
  actividad") y un `failure_error_type` claro. Usar el mismo patrón de transición de estado
  existente.
- El umbral debe ser holgado para no matar jobs que tardan legítimamente.

---

## Objetivo 3 — Copiar clave fiscal al clipboard (sin verla) + auditoría

**Problema:** No hay forma de recuperar la clave fiscal. Está encriptada (Fernet,
`crypto_service.py`), `clients.py` solo expone el flag `has_clave_fiscal`, nunca el valor.

**Decisión:** botón "copiar" que copia el valor desencriptado al clipboard **sin mostrarlo**
en pantalla (para verlo hay que pegarlo en otro lado). Acceso: cualquier usuario logueado,
pero **auditado** — queda registro en `audit_event` de quién copió la clave de qué cliente
y cuándo.

**Backend** (`backend/app/api/clients.py`, `crypto_service.py`, modelo `audit_event`):
- Nuevo endpoint `GET /clients/<id>/clave-fiscal` con `@require_auth` que:
  - desencripta con `decrypt_secret`; si es placeholder o no hay clave → 404/409 claro.
  - registra un `AuditEvent` (usuario actual, taxpayer_id, acción tipo
    `"clave_fiscal_copiada"`, timestamp) ANTES de devolver.
  - devuelve `{ "clave_fiscal": "<valor>" }`. No loguear el valor en logs.

**Frontend** (`frontend/src/ClientTable.tsx`):
- Botón "Copiar clave" por fila. Al click: fetch al endpoint, `navigator.clipboard.writeText`
  con el valor, feedback visual ("Copiada al portapapeles") **sin renderizar el valor**.
- Manejo de error si no hay clave cargada.

**Seguridad:** el valor viaja solo en la respuesta de ese request puntual y va directo al
clipboard; nunca se persiste en estado del frontend ni se muestra en el DOM.

---

## Objetivo 4 — Solo años con liquidaciones en el filtro de /coes

**Problema:** El dropdown de año en `CoesListPage.tsx` (líneas 438-446) está hardcodeado
(`currentYear+1` a `currentYear-5`), permitiendo elegir 2021 o 2027 sin datos.

**Decisión:** poblar el dropdown con los años que realmente tienen liquidaciones.

**Backend** (`backend/app/api/coes.py`):
- Nuevo endpoint `GET /coes/anios-disponibles` (o similar) que devuelve los años distintos
  presentes en `lpg_document`, derivados de la fecha de emisión, filtrando por
  `Taxpayer.activo` (consistente con la exclusión de inactivos ya implementada en /coes).
- Orden descendente.

**Frontend** (`CoesListPage.tsx`, hook nuevo o en `useCoesFilters.ts`):
- Reemplazar el rango hardcodeado por los años del endpoint (TanStack Query, cacheado).
- Si no hay años (DB vacía), el selector queda sin opciones de año.

---

## Objetivo 5 — Sesión expira a los pocos minutos

**Problema (causa raíz confirmada):** access token de **15 min** (`auth_service.py:10`),
SIN refresh automático. `fetchWithAuth` (`api/client.ts:45`) ante un 401 desloguea de
inmediato en vez de refrescar. El endpoint `/auth/refresh` YA existe (refresh token 7 días
en sessionStorage) pero el frontend solo lo usa al iniciar la app (`restoreSession`).

**Decisión:** lo estable y recomendado — token de vida razonable + refresh automático
mientras hay actividad.

**Backend** (`backend/app/services/auth_service.py`):
- Subir `ACCESS_TOKEN_EXPIRES_SECONDS` de 15 min a 60 min.

**Frontend** (`frontend/src/api/client.ts`, `store/useAuthStore.ts`):
- Cambiar el comportamiento ante 401 en `fetchWithAuth`: si hay refresh token y no se está
  restaurando, intentar `/auth/refresh` UNA vez, actualizar el access token y reintentar el
  request original. Solo si el refresh falla → `clearAuth()` + redirect a login.
- Evitar loops: el reintento se hace una sola vez por request; refrescos concurrentes se
  coalescen en una sola promesa.

---

## Estrategia de implementación

- Cada objetivo se delega a un sub-agente. Los 5 son independientes entre sí (tocan archivos
  distintos), salvo coincidencias menores; se delegan en paralelo.
- Tras la implementación, un agente con contexto fresco revisa los 5 diffs
  (correctness, seguridad de la clave fiscal y la auditoría, regresiones, consistencia con
  patrones del repo) y reporta CRITICAL/WARNING/SUGGESTION antes de cerrar.
- Verificación: `pytest` backend (incluyendo casos nuevos para obj 2/3/4), `tsc --noEmit`
  y `npm run build` en frontend, y prueba manual contra los datos reales restaurados.

## Tests

- **Obj 1:** stats mensuales cuentan correctamente COEs y completados de un mes dado;
  no incluyen docs de otros meses ni de taxpayers inactivos.
- **Obj 2:** un job `running` con `updated_at` viejo pasa a `failed`; uno reciente NO se toca.
- **Obj 3:** endpoint devuelve clave desencriptada y crea un `AuditEvent`; placeholder/sin
  clave → error claro; requiere auth.
- **Obj 4:** endpoint devuelve solo años con docs de taxpayers activos, ordenados desc.
- **Obj 5:** (frontend) un 401 dispara refresh y reintento; refresh fallido desloguea.
  (backend) verificar el nuevo TTL.
