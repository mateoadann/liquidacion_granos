# Feature 076 — Panel de salud de extracciones

**Fecha:** 2026-06-23
**Rama:** `feature/076-panel-salud-extracciones` (desde `dev`)
**Estado:** Diseño aprobado

## Problema

El proceso de extracción corre **una vez por día a las 3 AM (Argentina)** contra cada
contribuyente activo, consultando los COEs de los últimos 30 días en AFIP/ARCA vía
Playwright. Hoy el sistema **no ofrece ninguna forma de saber qué extracciones
fallaron, por qué, ni hace cuántos días un cliente está caído**.

Dos consecuencias concretas, verificadas sobre la DB de producción
(70 contribuyentes, 1556 jobs, rango 2026-04-01 → 2026-06-18):

1. **No se sabe qué cambiar.** Ej.: el contribuyente id=30 lleva desde 2026-06-10 sin
   una extracción exitosa (8 días, 11 fallos), por `auth_failed` (clave fiscal
   incorrecta) durante 5 días y luego `timeout`. La causa es accionable pero nadie la ve.
2. **Un cliente puede quedar caído todo el mes** y, si emitió liquidaciones, esas no se
   cargan. Ej.: contribuyente id=6 nunca tuvo una extracción exitosa.

Objetivo de negocio: que las extracciones diarias sean exitosas al ~99%, y que cuando
algo requiera intervención humana, el usuario lo vea de inmediato y sepa qué corregir.

## Alcance (feature 076)

**Solo lectura.** Panel "Salud de extracciones" + endpoint de agregación. Sin acciones
(reintentar, editar) ni reporte diario push — esos son features posteriores (077/078)
que se apoyan en esta base.

No se toca el pipeline de Playwright ni el scheduler. La feature **lee y agrega** la
data ya persistida en `extraction_job`.

## Datos disponibles (ya existentes)

`extraction_job` ya persiste por job:
- `status` (`completed` | `failed` | `partial` | ...)
- `failure_phase`, `failure_error_type`
- `failure_message_user` (mensaje en español orientado al estudio contable)
- `failure_message_technical` (código + detalle técnico)
- `finished_at`, `created_at`, `taxpayer_id`

`extraction_failure_mapper.map_failure(phase, error_type, dropdown_clicked)` ya traduce
(fase + tipo de error) → `(mensaje_usuario, mensaje_técnico)`. El mensaje técnico ya
incluye un **código estable** al inicio (`AUTH_FAILED at login | ...`,
`SERVICE_NOT_ADHERED | ...`, `NETWORK_ERROR | ...`, etc.).

## Arquitectura

```
extraction_job (datos ya persistidos)
        │
        ▼
GET /api/extracciones/salud  ──>  agrega por cliente activo, clasifica semáforo
        │
        ▼
Vista React "Salud de extracciones" (TanStack Query, solo lectura)
```

## Cambio de datos: columna `failure_code`

El semáforo necesita el código estable (`AUTH_FAILED` vs `TRANSIENT_LOGIN`) para
decidir rojo vs amarillo. Hoy ese código solo vive embebido en
`failure_message_technical`.

**Decisión:** agregar columna `failure_code VARCHAR(40) NULL` a `extraction_job` y que
`map_failure` devuelva el código como tercer valor explícito, persistido al fallar.
Se descarta el parseo del string técnico: acopla el panel al formato exacto del mensaje
y se rompería en silencio si ese texto cambia.

- `map_failure` pasa a devolver `(user_es, tech_en, code)`.
- El worker (`playwright_jobs.py`) persiste `failure_code` junto a los otros campos de fallo.
- **Jobs viejos** (sin `failure_code`): se clasifican como **gris/desconocido**.
  No hay backfill — la feature 075 (ya mergeada) asegura que de acá en adelante todos
  los fallos preserven fase y código; los ~56 fallos históricos son historia.

Códigos conocidos del mapper:
`AUTH_FAILED`, `SERVICE_NOT_ADHERED`, `EMPRESA_NOT_FOUND`, `TRANSIENT_LOGIN`,
`ARCA_SLOW_AFTER_DROPDOWN`, `OPEN_SERVICE_TIMEOUT`, `CONSULTA_FAILURE`,
`NETWORK_ERROR`, `WS_COE_ERRORS`, `UNKNOWN_ERROR`.

## Endpoint: `GET /api/extracciones/salud`

Devuelve una fila por **contribuyente activo** (`taxpayer.activo = True`), ya
clasificada y ordenada.

### Lógica por cliente

1. **Último job** del cliente (cualquier `operation`: nocturna, retry o manual), por `created_at` desc.
2. `ultima_ok` = `max(finished_at)` de jobs `status='completed'`. `null` → nunca extrajo.
3. `dias_sin_exito` = días entre `ultima_ok` y hoy (timezone America/Argentina/Cordoba). `null` si nunca.
4. `estado` (semáforo), derivado del **último job**:
   - **verde**: último job `completed` (sin importar la fecha). Decisión: si la
     última extracción fue exitosa, el cliente está sano. Como el scheduler corre
     a diario contra cada cliente activo, el último job normalmente es el de hoy;
     el caso de un éxito "viejo" (el scheduler dejó de correrle) es raro y se
     acepta conscientemente que se muestre verde — no se penaliza por antigüedad
     un resultado exitoso.
   - **rojo**: último job fallido con causa **accionable** —
     `failure_code ∈ {AUTH_FAILED, SERVICE_NOT_ADHERED, EMPRESA_NOT_FOUND}`.
   - **amarillo**: último job fallido con causa **transitoria** —
     `failure_code ∈ {TRANSIENT_LOGIN, NETWORK_ERROR, ARCA_SLOW_AFTER_DROPDOWN,
     OPEN_SERVICE_TIMEOUT, CONSULTA_FAILURE, WS_COE_ERRORS, UNKNOWN_ERROR}`.
     Sube a **rojo** si `dias_sin_exito >= 3`.
   - **gris**: cliente sin ningún job, o último job fallido con `failure_code` nulo
     (job viejo / causa sin clasificar).

### Ordenamiento

rojo → amarillo → gris → verde; dentro de cada grupo por `dias_sin_exito` desc (lo más
urgente arriba).

### Forma de respuesta (snake_case)

```json
{
  "generado_en": "2026-06-23T10:40:00",
  "resumen": { "verde": 62, "amarillo": 4, "rojo": 3, "gris": 1 },
  "clientes": [
    {
      "taxpayer_id": 30,
      "razon_social": "El Socorro SRL",
      "cuit": "20...",
      "estado": "rojo",
      "dias_sin_exito": 8,
      "ultima_ok": "2026-06-10",
      "causa_codigo": "AUTH_FAILED",
      "causa_mensaje": "La clave fiscal de la empresa parece ser incorrecta. Verificá las credenciales.",
      "es_accionable": true
    }
  ]
}
```

- `causa_codigo` / `causa_mensaje`: del último job fallido. `null` en verde.
- `es_accionable`: `true` cuando el estado es rojo por causa accionable (ayuda al
  frontend a destacar la fila). Las causas transitorias son `false`.

## Frontend

Vista "Salud de extracciones" (ruta/tab nueva, siguiendo el patrón de páginas existentes
como `ClientsPage`/`ClientTable`).

- **Cards de resumen** arriba: contador por color (🟢/🟡/🔴/⚪), mismo estilo que el
  dashboard mensual existente.
- **Tabla** ordenada por gravedad:
  - Razón social + CUIT
  - Badge de estado (color)
  - Días sin éxito (o "Nunca")
  - Causa accionable (`causa_mensaje`) — visible solo en rojo/amarillo
  - Última extracción OK (fecha)
- TanStack Query contra `GET /api/extracciones/salud`. Solo lectura, sin mutaciones.
- Adapters snake→camel centralizados según convención (`clients.ts`).

## Testing

### Backend (pytest, TDD)

Tests de la lógica de clasificación del endpoint (casos derivados de la data real):
- último job `completed` hoy → verde
- `AUTH_FAILED` → rojo desde día 1
- `TRANSIENT_LOGIN` con 1 día → amarillo; con 3+ días → rojo
- cliente sin jobs → gris, `dias_sin_exito = null`
- cliente con `ultima_ok` null pero con fallos → gris/"nunca"
- `failure_code` null (job viejo fallido) → gris
- contribuyente inactivo → excluido del resultado
- ordenamiento rojo → amarillo → gris → verde

Tests de `map_failure`: devuelve el código correcto como tercer valor de la tupla, para
cada rama del mapper.

### Frontend

`cd frontend && npx tsc --noEmit` + `npm run build` (no hay runner de tests en front).

## Fuera de alcance (features futuras)

- 077: botón "reintentar" desde el panel (re-encolar extracción de un cliente caído).
- 078: reporte/mensaje diario push post-3AM (email u otro canal) — reusa la lógica de
  agregación de este endpoint.

## Archivos afectados (estimado)

- `backend/migrations/versions/*` — migración: columna `failure_code`
- `backend/app/models/extraction_job.py` — campo `failure_code`
- `backend/app/services/extraction_failure_mapper.py` — `map_failure` devuelve código
- `backend/app/workers/playwright_jobs.py` — persistir `failure_code`
- `backend/app/api/extracciones.py` (o blueprint existente) — endpoint `/salud`
- `backend/tests/unit/test_extraccion_salud.py` — nuevo
- `backend/tests/unit/test_extraction_failure_mapper.py` — actualizar a tupla de 3
- `frontend/src/` — página + tabla + hook + tipos/adapters
