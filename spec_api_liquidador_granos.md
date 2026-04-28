# SPEC — API + estado de COEs (liquidador-granos)

**Proyecto:** liquidador-granos (repositorio externo)
**Feature:** API REST para recibir reportes de carga de rpa-holistor + tracking
            de estado de cada COE + extensión del JSON emitido a v7.1.
**Estado:** spec aprobado, pendiente implementación
**Depende de:** [docs/integracion_ledger_coes.md](integracion_ledger_coes.md) (diseño global)
**Cross-ref:** [docs/spec_ledger_rpa_holistor.md](spec_ledger_rpa_holistor.md) (contraparte)

> Este SPEC vive en el repo `rpa-holistor` pero describe trabajo para
> `liquidador-granos`. Copiar al otro repo al arrancar la implementación.

---

## 1. Objetivo

1. Tracking de estado de cada COE (`pendiente → descargado → cargado | error`) dentro de liquidador-granos.
2. Exponer API REST para que rpa-holistor reporte COEs cargados.
3. Incluir `coe` + metadata en el JSON v7.1 que consume rpa-holistor.
4. Filtrar COEs ya `cargado` al emitir nuevos batches (no re-enviarlos).

## 2. Scope

**Dentro:**
- Tabla `coes_estado` (o equivalente) en la DB existente de liquidador-granos.
- Endpoints REST (FastAPI): health, reportar cargado, consultar estado, listar estados.
- Auth por `X-API-Key` con valor en `.env`.
- Cambio en el emisor del JSON: versión `v7.1`, agregar `schema_version`, `meta`, y por liquidación `coe`, `id_liquidacion`, `estado_origen`.
- Transición automática de estado al descargar LPG (`pendiente → descargado`) y al recibir reporte (`descargado → cargado | error`).
- Filtrado: no incluir COEs con `estado='cargado'` en JSONs futuros (a menos que se fuerce via flag).

**Fuera:**
- UI/dashboard (fuera de v1 — inspección por endpoints o DB directa).
- Lógica de reintento desde el servidor hacia rpa-holistor (el cliente reintenta, no el server).
- Webhooks a terceros.
- Auth multi-usuario / OAuth.

## 3. Precondiciones (asumidas)

- liquidador-granos consume WebService LPG de Arca y emite un JSON consumido por rpa-holistor.
- Existe persistencia (SQL o similar) donde ya se guardan datos de LPG.
- Stack Python (consistente con el resto del ecosistema).
- Puede correr un proceso adicional (uvicorn) en la misma máquina o una cercana.

Si algo no se cumple, ajustar el SPEC antes de implementar.

## 4. Entregables

### Nuevos

| Path sugerido | Descripción |
|---|---|
| `api/__init__.py` | Paquete |
| `api/app.py` | FastAPI app con los endpoints |
| `api/schemas.py` | Modelos Pydantic de request/response |
| `api/auth.py` | Middleware `X-API-Key` |
| `api/service.py` | Lógica de negocio (upsert, filtros, transiciones) |
| `db/migrations/NNN_coes_estado.sql` | Migración de la tabla (o equivalente ORM) |
| `tests/test_api_coes.py` | Tests de endpoints |
| `.env.example` | Template con variables |
| `Dockerfile` o `docker-compose.yml` | Opcional, si se despliega containerizado |

### Modificados

| Path | Cambio |
|---|---|
| Módulo emisor de JSON | Emitir `schema_version="v7.1"`, `meta`, y por liquidación `coe`, `id_liquidacion`, `estado_origen`. Transicionar COEs a `descargado` al emitir. Filtrar `cargado` al seleccionar candidatos. |
| Módulo de ingesta LPG | Al insertar un COE nuevo desde Arca, estado inicial = `pendiente`. |
| `README.md` | Sección "API de integración con rpa-holistor" |
| `.gitignore` | Agregar `.env` |
| `requirements.txt` | Agregar `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `python-dotenv` |

## 5. Modelo de datos

### Tabla `coes_estado`

```sql
CREATE TABLE coes_estado (
    coe                   TEXT PRIMARY KEY,              -- 14 dígitos
    cuit_empresa          TEXT NOT NULL,
    cuit_comprador        TEXT,
    codigo_comprobante    TEXT,                          -- F1 | F2 | NL
    tipo_pto_vta          INTEGER,
    nro_comprobante       INTEGER,
    fecha_emision         TEXT,                          -- ISO YYYY-MM-DD
    id_liquidacion        TEXT UNIQUE,                   -- UUID generado acá al descargar

    estado                TEXT NOT NULL,                 -- pendiente | descargado | cargado | error
    descargado_en         TEXT,                          -- ISO 8601
    cargado_en            TEXT,                          -- ISO 8601
    error_mensaje         TEXT,
    error_fase            TEXT,

    ultima_ejecucion_id   TEXT,                          -- del RPA — última que reportó
    ultimo_usuario        TEXT,
    hash_payload_emitido  TEXT,                          -- lo que mandamos en el JSON
    hash_payload_cargado  TEXT,                          -- lo que el RPA reporta de vuelta

    actualizado_en        TEXT NOT NULL                  -- ISO 8601, touch on every update
);

CREATE INDEX idx_coes_estado_empresa_estado ON coes_estado(cuit_empresa, estado);
CREATE INDEX idx_coes_estado_actualizado ON coes_estado(actualizado_en);
```

### Transiciones permitidas

```
pendiente   → descargado   (al emitir JSON que incluye este COE)
descargado  → cargado      (POST /coes/cargado estado=ok)
descargado  → error        (POST /coes/cargado estado=error)
error       → cargado      (POST /coes/cargado estado=ok — reintento exitoso)
error       → descargado   (manual, al re-emitir JSON)
cargado     → cargado      (no-op, idempotente)
```

Cualquier otra transición → 409 Conflict.

### Reglas de hash

- `hash_payload_emitido` se calcula al momento de incluir el COE en un JSON,
  con el mismo algoritmo que usa rpa-holistor (ver sección 8).
- `hash_payload_cargado` viene en el `POST /coes/cargado` desde el RPA.
- Si al recibir un report los hashes difieren → guardar ambos + devolver `409 payload_mismatch`.

## 6. Endpoints

### Base URL

`http://<host>:8765/v1`

Puerto sugerido: **8765** (no colisiona con servicios comunes). Configurable via `.env`.

### Auth

Todos los endpoints excepto `/health` requieren header `X-API-Key: <key>`.
Key configurada en `.env` como `LIQUIDADOR_API_KEY`. Responde `401 api_key_invalida` si no matchea.

### `GET /v1/health`

Liveness probe. Sin auth.

```jsonc
// 200
{ "status": "ok", "timestamp": "2026-04-24T10:45:12-03:00", "version": "1.2.3" }
```

### `POST /v1/coes/cargado`

El endpoint más importante. rpa-holistor lo llama al final de F14 exitoso o ante un FAIL.

**Request:**

```jsonc
{
  "coe": "12345678901234",                       // requerido, 14 dígitos
  "ejecucion_id": "run_uuid_xyz",                // requerido
  "usuario": "mateo.adan",                       // requerido
  "cargado_en": "2026-04-24T10:45:12-03:00",     // ISO 8601 con TZ, requerido
  "estado": "ok",                                // ok | error
  "hash_payload": "sha256:...",                  // requerido

  "comprobante": {                               // requerido si estado=ok
    "codigo": "F2",
    "tipo_pto_vta": 3302,
    "nro": 30384098,
    "fecha_emision": "2026-02-26"
  },

  "error_fase": null,                            // requerido si estado=error
  "error_mensaje": null
}
```

**Responses:**

```jsonc
// 200 OK (primera vez o idempotente con mismo hash)
{
  "coe": "12345678901234",
  "estado_registrado": "cargado",   // o "error"
  "duplicado": false                // true si ya estaba con el mismo hash+ejecucion_id
}

// 409 Conflict — hash distinto
{
  "error": "payload_mismatch",
  "mensaje": "El hash del payload difiere del emitido.",
  "detalle": {
    "hash_emitido": "sha256:abc...",
    "hash_recibido": "sha256:def..."
  }
}

// 409 Conflict — transición inválida
{
  "error": "transicion_invalida",
  "mensaje": "No se puede pasar de 'pendiente' a 'cargado' sin descargar primero.",
  "detalle": { "estado_actual": "pendiente" }
}

// 401 — api key inválida
{ "error": "api_key_invalida", "mensaje": "X-API-Key faltante o inválida." }

// 422 — validación Pydantic
{ "error": "validacion_fallida", "mensaje": "...", "detalle": {...} }

// 500 — error interno
{ "error": "interno", "mensaje": "...", "detalle": {...} }
```

**Idempotencia:** mismo `(coe, ejecucion_id, hash_payload, estado)` → `duplicado: true`, no vuelve a grabar. Mismo `coe` con `ejecucion_id` distinto pero mismo `estado` y `hash` → se actualiza `ultima_ejecucion_id` + `actualizado_en`, `duplicado: false`.

### `GET /v1/coes/{coe}`

Estado actual de un COE. Para debugging / verificación puntual desde rpa-holistor.

```jsonc
// 200
{
  "coe": "12345678901234",
  "cuit_empresa": "30711165378",
  "cuit_comprador": "30708729929",
  "id_liquidacion": "liq_abc123",
  "estado": "cargado",
  "descargado_en": "2026-04-23T18:00:00-03:00",
  "cargado_en": "2026-04-24T10:45:12-03:00",
  "ultima_ejecucion_id": "run_uuid_xyz",
  "ultimo_usuario": "mateo.adan",
  "comprobante": {
    "codigo": "F2",
    "tipo_pto_vta": 3302,
    "nro": 30384098,
    "fecha_emision": "2026-02-26"
  }
}

// 404
{ "error": "coe_no_encontrado", "mensaje": "COE 12345678901234 no existe en la base." }
```

### `GET /v1/coes/estados`

Listado con filtros. Para dashboard / conciliación.

Query params:
- `cuit_empresa` (opcional)
- `estado` (opcional): `pendiente` | `descargado` | `cargado` | `error`
- `desde`, `hasta` (opcionales, ISO date)
- `limit` (default 100, max 500)
- `offset` (default 0)

```jsonc
// 200
{
  "total": 234,
  "items": [ { /* como GET /v1/coes/{coe} */ }, ... ]
}
```

### `POST /v1/coes/{coe}/forzar-estado` — (opcional, admin only)

Para correcciones manuales. Body: `{ "estado": "...", "razon": "..." }`.
Requiere header adicional `X-Admin-Token`. Queda fuera de v1 si no hay necesidad.

## 7. Cambio al JSON emitido (v7 → v7.1)

### Al seleccionar COEs para un nuevo JSON

```python
# Pseudocódigo
candidatos = db.query(
    "SELECT * FROM coes_estado "
    "WHERE cuit_empresa = ? AND estado IN ('pendiente', 'descargado') "
    "AND (fecha_emision BETWEEN ? AND ?)",
    cuit_empresa, desde, hasta
)
# NO incluir 'cargado'. 'error' queda excluido por default
# (el usuario los re-emite explícitamente con un flag si corresponde).
```

### Al emitir

1. Generar `batch_id` (ej. `b_YYYYMMDD_HHMMSS`).
2. Para cada liquidación seleccionada:
   - Asignar `id_liquidacion` si no tiene.
   - Calcular `hash_payload_emitido` (ver sección 8).
   - Transicionar `pendiente → descargado`, `descargado → descargado` (no-op, pero `descargado_en` se puede actualizar).
   - Guardar `hash_payload_emitido` y `descargado_en`.
3. Escribir JSON con estructura v7.1:

```jsonc
{
  "schema_version": "v7.1",
  "meta": {
    "generado_en": "2026-04-24T10:30:00-03:00",
    "generador": "liquidador-granos@1.2.3",
    "batch_id": "b_20260424_103000"
  },
  "liquidaciones": [
    {
      "coe": "12345678901234",
      "id_liquidacion": "liq_abc123",
      "estado_origen": "descargado",

      "cuit_empresa": "30711165378",
      "mes": 2,
      "anio": 2026,
      "cuit_comprador": "30708729929",
      "cuit_proveedor": "20102139063",

      "comprobante": { /* igual que v7 */ },
      "grano": { /* igual que v7 */ },
      "retenciones": [ /* igual que v7 */ ],
      "deducciones": [ /* igual que v7 */ ]
    }
  ]
}
```

### Retrocompatibilidad

- Emisor de JSON **solo soporta v7.1**. No hay modo legacy.
- Si se necesita compatibilidad hacia atrás (ej. pipelines viejos), agregar flag CLI `--schema-version=v7` que desactive campos nuevos. No recomendado.

## 8. Cálculo de `hash_payload` (contrato compartido)

Debe ser **idéntico** al que usa rpa-holistor. Algoritmo:

```python
import hashlib, json

def calcular_hash(liquidacion: dict) -> str:
    # Excluir campos de metadata que no afectan el contenido cargable
    campos_excluidos = {"estado_origen", "id_liquidacion"}
    payload = {k: v for k, v in liquidacion.items() if k not in campos_excluidos}
    serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serializado.encode("utf-8")).hexdigest()
```

Consideraciones:
- `sort_keys=True` es crítico — garantiza estabilidad entre Python versions / plataformas.
- Excluir campos que pueden cambiar entre emisiones sin cambiar el "contenido de negocio".
- Si algún día se agrega un campo nuevo que NO debe afectar el hash, agregar a `campos_excluidos`. Ambos repos deben updatearse juntos.

## 9. Configuración (`.env`)

```
LIQUIDADOR_API_HOST=0.0.0.0
LIQUIDADOR_API_PORT=8765
LIQUIDADOR_API_KEY=<random_string_32_chars>
LIQUIDADOR_API_DEBUG=false

# DB (según lo que ya use el proyecto)
DATABASE_URL=...
```

Key suggestion: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 10. Deployment

### Opción mínima — misma máquina que rpa-holistor

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8765 --workers 1
```

Con un único worker alcanza: el tráfico esperado es `<100 reqs/hora` (un usuario
operando el RPA). SQLite-friendly.

### Opción recomendada — systemd service / Windows service

Para que arranque al bootear el servidor donde corre liquidador-granos.

### Red

- Si rpa-holistor corre en la misma VM → `LIQUIDADOR_API_URL=http://localhost:8765`.
- Si en VMs distintas → exponer puerto 8765 en red interna, `LIQUIDADOR_API_URL=http://<ip-interna>:8765`.
- Nunca exponer a internet público — no hay auth robusta, solo API key.

### Logging

- Loggear todo request con `coe`, `ejecucion_id`, `estado`, código de respuesta.
- Archivo rotativo por día.
- Errores 5xx → nivel ERROR, con traceback.

## 11. Criterios de aceptación

- [ ] Al descargar un COE nuevo de Arca → estado `pendiente`.
- [ ] Al emitir JSON v7.1 → COEs pasan a `descargado`, se persiste `hash_payload_emitido`.
- [ ] JSON v7.1 emitido valida contra el schema definido en sección 7.
- [ ] `POST /v1/coes/cargado` con `estado=ok` → COE pasa a `cargado`, devuelve 200.
- [ ] `POST /v1/coes/cargado` idempotente — mismo payload 2x → 200 + `duplicado: true` la 2da.
- [ ] Hash mismatch → 409 con detalle.
- [ ] Transición inválida (ej. `cargado → pendiente` sin flag admin) → 409.
- [ ] Sin header `X-API-Key` → 401.
- [ ] `GET /v1/coes/{coe}` para COE inexistente → 404.
- [ ] Al generar el próximo JSON, los COEs `cargado` NO aparecen.
- [ ] `GET /v1/health` responde sin auth.
- [ ] Logs capturan request + response + latencia.

## 12. Tests

### `tests/test_api_coes.py`

- `test_health_sin_auth`
- `test_endpoints_sin_api_key_devuelven_401`
- `test_post_cargado_ok_descargado_a_cargado`
- `test_post_cargado_idempotente`
- `test_post_cargado_hash_mismatch_409`
- `test_post_cargado_desde_estado_invalido_409`
- `test_post_cargado_error_guarda_fase_y_mensaje`
- `test_get_coe_existente`
- `test_get_coe_inexistente_404`
- `test_listado_filtros_y_paginacion`

### `tests/test_emisor_json.py`

- `test_json_incluye_schema_version_v7_1`
- `test_json_incluye_meta_con_batch_id`
- `test_cada_liquidacion_tiene_coe`
- `test_coes_cargados_no_se_incluyen`
- `test_hash_emitido_es_estable`
- `test_transicion_pendiente_a_descargado_al_emitir`

### `tests/test_hash_shared.py`

**Crítico:** test que valide que el hash producido acá es idéntico al de rpa-holistor.
Mantener un fixture JSON compartido (`tests/fixtures/hash_contract.json`) con
`{"input": {...}, "hash_esperado": "sha256:..."}`. Ambos repos deben pasar el
mismo test con el mismo fixture.

## 13. Plan de implementación (orden sugerido)

1. **Migración DB** (1h) — crear tabla `coes_estado`, poblar desde datos existentes si los hay (estado inicial `descargado` si ya se emitió, si no `pendiente`).
2. **Cambio al emisor JSON** (2h) — schema v7.1, transición `pendiente → descargado`, filtro de `cargado`. Coordinar con rpa-holistor para testear con un JSON real.
3. **FastAPI skeleton + auth + health** (1h) — proyecto corre, endpoint base funciona.
4. **POST /v1/coes/cargado** (2h) — lógica de transición, idempotencia, hash check.
5. **GET /v1/coes/{coe} + listado** (1h).
6. **Tests** (2h).
7. **Deployment + logging** (1h).
8. **Integración end-to-end con rpa-holistor** (1-2h) — flipear el flag `LIQUIDADOR_API_ENABLED=true` en el otro lado y probar flujo completo.

## 14. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Hash no matchea por diferencias de serialización | Test fixture compartido entre repos (sección 12) |
| Se emite un COE pero nunca llega reporte → queda en `descargado` para siempre | Job/endpoint de "reconciliación" — fuera de v1, pero previsto |
| rpa-holistor reporta con `ejecucion_id` nuevo pero datos iguales | Idempotencia basada en `(coe, hash)`, no en `ejecucion_id` |
| API key se filtra | Rotación documentada + scope limitado a red interna |
| Transiciones concurrentes sobre el mismo COE | Lock optimista con `UPDATE ... WHERE estado = <esperado>` + retry |
| Crece mucho la tabla | Particionado por año o archivado después de N meses — fuera de v1 |

## 15. Fuera de v1

- Dashboard web con gráficos.
- Webhooks hacia rpa-holistor (server → RPA) para invalidar un COE ya cargado.
- Auth multi-usuario con roles.
- Export masivo del estado en CSV/Parquet.
- Métricas Prometheus.
