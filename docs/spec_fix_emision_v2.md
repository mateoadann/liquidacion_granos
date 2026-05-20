# SPEC — Fix de emisión en `GET /v2/liquidaciones`

**Proyecto:** `liquidacion_granos`
**Doc complementario:**
- `docs/base_funcional_tecnica_wslpg.md` — contrato base
**Status:** aprobado, pendiente implementación
**Fecha:** 2026-05-20

---

## 1. Síntoma observado en producción

Tras cargar exitosamente una liquidación en Holistor (RPA completa F14),
`POST /v1/coes/cargado` siempre devuelve `409 hash_mismatch`. Esto se repite
con el endpoint del visor del ledger "Reintentar sincronización" y también
con la llamada inmediata post-F14.

### Diagnóstico

Query a `GET /v1/coes/{coe}` sobre los COEs afectados devolvió en TODOS:

```jsonc
{
  "coe": "330230656361",
  "estado": "cargado",                        // post-forzado manual
  "hash_payload_emitido": null,               // ⚠ NUNCA SE SETEÓ
  "hash_payload_cargado": "sha256:69af283…",  // lo que RPA mandó (OK)
  "descargado_en": null,                      // ⚠ NUNCA TRANSICIONÓ
  "forzado": true,                            // workaround usado
}
```

El RPA computa su `hash_payload_cargado` con `calcular_hash(liquidacion)`
sobre el dict v7.1 tal como vino del server. El problema es que el server
nunca persistió `hash_payload_emitido` al emitir, así que cualquier valor en
`hash_payload_cargado` se compara contra `null` → siempre `hash_mismatch`.

## 2. Causa raíz

`build_json_v7_bulk` es explícitamente read-only (docstring línea 267-286
de `json_v7_exporter.py`): no llama `marcar_descargado`, no persiste
`hash_payload_emitido`, no transiciona estado. Esto rompe la cadena de
validación en `reportar_cargado` (línea 173 de `coe_estado_service.py`):

```python
if estado_reporte == "ok" and hash_recibido != entry.hash_payload_emitido:
    raise HashMismatchError(...)
```

Si `hash_payload_emitido` es `None` → siempre lanza `HashMismatchError`.

## 3. Scope

**Dentro:**
- `GET /v2/liquidaciones` persiste `hash_payload_emitido` y transiciona
  `pendiente → descargado` por cada COE incluido en el response.
- Idempotencia: re-llamar el GET sobre los mismos COEs no re-setea ni rota
  hashes ni timestamps. La primera emisión es fuente de verdad.
- Misma transacción para SELECT + UPDATE: o se persisten los side-effects y
  se devuelve el response, o rollback completo. Sin estados intermedios.
- Tests unitarios de side-effects + test end-to-end (emitir → reportar → cargado).

**Fuera:**
- Cambios en `POST /v1/coes/cargado`. La validación de hash sigue igual.
- Filtros nuevos en el GET.
- Cambios al schema `coe_estado` (las columnas ya existen).
- Side-effects sobre COEs ya en estado `cargado` / `error`.

## 4. Precondiciones verificadas

- `CoeEstado` con columnas `hash_payload_emitido`, `descargado_en`, `estado`
  ya existe (`backend/app/models/coe_estado.py`). No se necesita migración.
- `coe_estado_service.calcular_hash()` ya implementado (línea 58).
- `coe_estado_service.marcar_descargado()` ya implementado (línea 116) — hace
  exactamente lo que el fix necesita: setea hash, descargado_en y estado.
- `GET /v2/liquidaciones` operativo en `backend/app/api/integration.py` (línea 197).
- `POST /v1/coes/cargado` operativo y validando contra `hash_payload_emitido`.

## 5. Entregables

### Modificados

| Path | Cambio |
|---|---|
| `backend/app/services/json_v7_exporter.py` | `build_json_v7_bulk` devuelve `(body, coes_a_persistir)` donde `coes_a_persistir` es lista de `(coe_estado_id, hash_calculado)`. No persiste nada — sigue siendo stateless. |
| `backend/app/api/integration.py` | `get_v2_liquidaciones` abre transacción única, llama `build_json_v7_bulk`, aplica side-effects idempotentes, commit, devuelve 200. |

### Nuevos

| Path | Rol |
|---|---|
| `backend/tests/integration/test_v2_emision_side_effects.py` | Tests de side-effects: primera llamada setea, re-llamadas no pisan, COEs en `cargado` no se tocan, rollback ante fallo. |
| `backend/tests/integration/test_v2_emision_e2e.py` | Test end-to-end: GET → POST cargado matchea hash → 200 ok. |

## 6. Diseño detallado

### 6.1 Separación de responsabilidades

`build_json_v7_bulk` permanece stateless (constructor de JSON). El endpoint
aplica los side-effects. Esto permite testear el constructor sin DB
transaccional y testear los side-effects de forma aislada.

```
endpoint → abre transacción
  → build_json_v7_bulk(docs)  →  (body, [(coe_estado_id, hash), ...])
  → _aplicar_side_effects_emision(coes_a_persistir)  →  UPDATEs idempotentes
  → commit (al salir del with)
→ return body 200
```

### 6.2 Comportamiento del nuevo `GET /v2/liquidaciones`

Por cada `CoeEstado` incluido en el response:

```
SI hash_payload_emitido IS NULL:
    hash_payload_emitido = calcular_hash(liquidacion_v71_dict)

SI descargado_en IS NULL:
    descargado_en = now_cordoba_naive()

SI estado = 'pendiente':
    estado = 'descargado'

(Si estado ya es 'descargado', 'cargado' o 'error': no tocar estado ni descargado_en.
 Si hash_payload_emitido ya está seteado: no tocar.)
```

Todos los UPDATEs en la misma transacción que el SELECT. Si cualquier paso
falla → rollback, no se devuelve el response.

### 6.3 Idempotencia

- **N=1** sobre COE en `pendiente`: setea hash, descargado_en, estado=descargado.
- **N=2** (mismo COE): hash, descargado_en y estado se preservan. Body incluye
  el COE igual (no se filtra por estado).

### 6.4 Hash calculado sobre qué

`calcular_hash` se aplica al mismo dict v7.1 que va al response, **después**
de toda la transformación. Usar siempre `coe_estado_service.calcular_hash`
(única implementación, nunca duplicar).

```python
CAMPOS_EXCLUIDOS_HASH = {"estado_origen", "id_liquidacion", "_hash_payload"}

def calcular_hash(liquidacion: dict) -> str:
    payload = {k: v for k, v in liquidacion.items() if k not in CAMPOS_EXCLUIDOS_HASH}
    serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serializado.encode("utf-8")).hexdigest()
```

### 6.5 Pseudo-código del endpoint

```python
@integration_bp.get("/v2/liquidaciones")
@require_api_key
def get_v2_liquidaciones():
    desde, hasta, cuits = _parsear_filtros(request)

    with db.session.begin():
        docs = _query_docs_filtrados(desde, hasta, cuits)
        body, coes_a_persistir = build_json_v7_bulk(docs, filtros)
        _aplicar_side_effects_emision(coes_a_persistir)

    return jsonify(body), 200


def _aplicar_side_effects_emision(coes: list[tuple[int, str]]) -> None:
    for coe_estado_id, hash_calc in coes:
        coe = CoeEstado.query.get(coe_estado_id)
        if coe.hash_payload_emitido is None:
            coe.hash_payload_emitido = hash_calc
        if coe.descargado_en is None:
            coe.descargado_en = now_cordoba_naive()
        if coe.estado == "pendiente":
            coe.estado = "descargado"
    # commit lo dispara el `with db.session.begin():` del caller
```

### 6.6 Cambio en `build_json_v7_bulk`

La función pasa de devolver `dict` a devolver `tuple[dict, list[tuple[int, str]]]`.

```python
# Antes
def build_json_v7_bulk(docs, filtros) -> dict:
    ...
    return body

# Después
def build_json_v7_bulk(docs, filtros) -> tuple[dict, list[tuple[int, str]]]:
    ...
    # coes_a_persistir: [(coe_estado.id, hash_calculado), ...]
    # Solo para COEs que tienen CoeEstado row (coe_estado_entry is not None)
    return body, coes_a_persistir
```

### 6.7 Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cliente cancela mid-flight: UPDATEs commiteados pero body perdido. | Idempotencia: próximo GET devuelve el mismo COE con el mismo hash. No hay divergencia. |
| Race condition entre dos clientes simultáneos. | `with db.session.begin()` + SQLAlchemy serializa por conexión. Para v2 el volumen no justifica `SELECT FOR UPDATE`; agregar si se detecta contención. |
| Drift entre `calcular_hash` del exporter y la versión en POST. | Una sola implementación en `coe_estado_service.calcular_hash`. Test unitario que verifica que ambos lados usan la misma función. |

## 7. Tests

### 7.1 `test_v2_emision_side_effects.py`

- Seed: `CoeEstado` en `pendiente`, `hash_payload_emitido=None`, `descargado_en=None`.
- `client.get("/api/v2/liquidaciones")` → 200.
- Assert: `hash_payload_emitido` seteado al hash del payload, `descargado_en` ~now(), `estado='descargado'`.

Idempotencia:
- Llamar 2x → `hash_payload_emitido` NO cambia, `descargado_en` NO cambia.

COE en `cargado`:
- GET lo devuelve, NO toca `hash_payload_emitido`, NO regresa estado.

Rollback:
- Forzar excepción dentro del bloque → COE queda con `hash_payload_emitido=None`.

### 7.2 `test_v2_emision_e2e.py`

1. Seed: 3 `CoeEstado` + `LpgDocument` + `taxpayer.scheduler_activo=True`.
2. `GET /api/v2/liquidaciones` → 200, 3 liquidaciones.
3. Por cada liq: `POST /v1/coes/cargado` con `hash_payload=calcular_hash(liq)`.
4. Assert: `200 ok` (NO `409 hash_mismatch`), `CoeEstado.estado='cargado'`,
   `hash_payload_cargado == hash_payload_emitido`.

Este test reproduce el bug: si la implementación sigue rota, el paso 3 falla con `409`.

## 8. Criterios de aceptación

- [ ] `GET /v2/liquidaciones` setea `hash_payload_emitido` y `descargado_en`
  la primera vez que incluye un COE en el response.
- [ ] Re-llamadas del GET son idempotentes — no rotan hashes ni timestamps
  ni regresan el estado.
- [ ] `POST /v1/coes/cargado` con hash computado desde la respuesta del GET
  devuelve `200 ok` (NO `409 hash_mismatch`).
- [ ] Suite del backend pasa 100%.
- [ ] Side-effects acotados a 3 columnas: `hash_payload_emitido`, `descargado_en`,
  `estado`. No se toca ningún otro campo de `coe_estado`.

## 9. Archivos afectados

| Archivo | Tipo de cambio |
|---|---|
| `backend/app/services/json_v7_exporter.py` | Modificación — `build_json_v7_bulk` devuelve tuple |
| `backend/app/api/integration.py` | Modificación — endpoint añade transacción + side-effects |
| `backend/tests/integration/test_v2_emision_side_effects.py` | Nuevo |
| `backend/tests/integration/test_v2_emision_e2e.py` | Nuevo |
