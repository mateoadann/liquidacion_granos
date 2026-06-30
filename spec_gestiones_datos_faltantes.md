# SPEC — Gestiones de datos faltantes (RPA-Holistor ↔ granos.estudiobavera.com)

**Proyectos involucrados:** `rpa-holistor` (cliente) + `granos.estudiobavera.com` (servidor / UI del personal).
**Feature:** Lazo bidireccional para que RPA-Holistor **avise** qué datos maestros faltan en Holistor para poder cargar una liquidación, el **personal del estudio** los dé de alta y marque cada gestión como hecha, y RPA **verifique** que el dato exista y **desbloquee** la(s) liquidación(es).
**Estado:** spec'eado, pendiente de implementación en ambos repos.
**Depende de / extiende:** [docs/spec_api_liquidador_granos.md](spec_api_liquidador_granos.md) (API v1/v2 existente, auth, idempotencia) · [docs/spec_ledger_rpa_holistor.md](spec_ledger_rpa_holistor.md) (ledger local).

> Este SPEC vive en el repo `rpa-holistor` pero describe trabajo para **ambos** lados.
>
> - **Parte A (§1–§7):** modelo conceptual y contrato HTTP compartido. **Léelo entero antes de implementar cualquiera de los dos lados.**
> - **Parte B (§8):** trabajo del lado **granos.estudiobavera.com** (servidor + UI del personal). **Esta es la parte que implementa el agente de granos** — está autocontenida y es la fuente de verdad del contrato.
> - **Parte C (§9–§12):** trabajo del lado **rpa-holistor** (cliente, ledger, extractores).

---

# Parte A — Modelo y contrato compartido

## 1. Objetivo y lazo end-to-end

Hoy, cuando una liquidación no se puede cargar en Holistor porque falta un dato maestro
(el cliente no existe, el grano no está mapeado a stock, etc.), el RPA falla y el personal
del estudio se entera por otra vía. Esta feature formaliza ese aviso y cierra el lazo:

```
1. RPA detecta faltantes   Al "Importar COEs", cruza cada liquidación nueva contra sus
                           lookups locales (clientes/proveedores/granos/cuentas, generados
                           desde las DBFs de Holistor). Cada dato que falta = una "gestión".

2. RPA → POST a granos     POST /v1/gestiones (batch). Crea una gestión por faltante,
                           idempotente. Estado inicial en granos: 'pendiente'.
                           La(s) liquidación(es) afectada(s) quedan 'bloqueada' en el ledger
                           local de RPA.

3. Personal del estudio    Ve el to-do en granos.estudiobavera.com, da de alta el cliente /
                           proveedor / grano / cuenta DENTRO de Holistor (manual), y marca
                           esa gestión como 'realizada' en la web. De a una (puede hacer 1
                           de 10).

4. RPA → GET a granos      Flujo MANUAL "Sincronizar gestiones": GET /v1/gestiones para leer
   + re-extract + verify   el estado. Para las 'realizada', re-extrae DIRIGIDO desde P:\ solo
                           las empresas/conjuntos involucrados, y verifica que el dato ahora
                           exista en el lookup.

5. RPA → POST a granos     POST /v1/gestiones/{gestion_id}/verificacion con resultado
   + desbloqueo             'verificada' (dato presente) o 'verificacion_fallida' (sigue sin
                           aparecer). Cuando TODAS las gestiones que bloquean una liquidación
                           quedan 'verificada', la liquidación vuelve a 'pendiente' (cargable).
```

**Invariante de responsabilidad (quién es dueño de cada transición):**

| Transición | Quién la dispara | Cómo |
|---|---|---|
| `(nueva)` → `pendiente` | RPA | `POST /v1/gestiones` |
| `pendiente` → `realizada` | **Personal** (UI granos) | botón "Marcar como hecha" |
| `verificacion_fallida` → `realizada` | **Personal** (UI granos) | re-marca tras corregir |
| `realizada` → `verificada` | RPA | `POST /v1/gestiones/{id}/verificacion` (ok) |
| `realizada` → `verificacion_fallida` | RPA | `POST /v1/gestiones/{id}/verificacion` (fallida) |

Cualquier otra transición → `409 transicion_invalida`.

## 2. Qué cuenta como "gestión"

**Regla:** *cualquier dato maestro que RPA necesite para cargar completa una liquidación y
que no exista todavía en los lookups locales de esa empresa.* Hoy son cuatro tipos:

| `tipo` | Qué falta | `identificador` | Origen del dato en Holistor (lo que el personal da de alta) |
|---|---|---|---|
| `alta_cliente` | El `cuit_comprador` no existe como cliente de la empresa | CUIT (14 díg.) | `<EMPRESA>/SUSCRIP.DBF` |
| `alta_proveedor` | Un `cuit_proveedor` (principal, o de una retención/deducción) no existe como proveedor | CUIT (14 díg.) | `<EMPRESA>/PROVEDOR.DBF` |
| `mapeo_grano` | El `cod_grano` de Arca no mapea a un ítem de stock agropecuario de la empresa | `cod_grano` Arca (ej. `"23"`) | `<EMPRESA>/STOCAGRO.DBF` |
| `alta_cuenta` | Un alias contable de retención/deducción no resuelve a una cuenta de la empresa | alias (ej. `"RIVA"`, `"PIB"`, `"RGAN"`) | `<EMPRESA>/cuentas.DBF` (campo `CALIAS`) |

El catálogo de tipos es **cerrado y compartido**: agregar un tipo nuevo requiere cambio
coordinado en ambos repos (nuevo valor del enum + lógica de verificación en RPA + render en granos).

## 3. Identidad de una gestión — `gestion_id` (contrato compartido)

Una gestión se identifica unívocamente por la tripleta `(tipo, cuit_empresa, identificador)`.
Para no acoplar los dos repos a un id autogenerado por la base, el `gestion_id` es
**determinístico** y se calcula igual en ambos lados (mismo espíritu que `calcular_hash`
de [§8 del spec API](spec_api_liquidador_granos.md)):

```python
import hashlib

def calcular_gestion_id(tipo: str, cuit_empresa: str, identificador: str) -> str:
    """ID determinístico de una gestión. Contrato compartido rpa-holistor ↔ granos.

    Normalización (CRÍTICA — ambos repos deben aplicarla idéntica):
      - tipo:          tal cual (enum snake_case en minúscula).
      - cuit_empresa:  solo dígitos (quitar '-', ' ', '.').
      - identificador: strip() + UPPER. (CUIT→dígitos en MAYÚS = igual; cod_grano→str;
                       alias 'riva'→'RIVA').
    """
    cuit = "".join(c for c in cuit_empresa if c.isdigit())
    ident = (identificador or "").strip().upper()
    base = f"{tipo}|{cuit}|{ident}"
    return "g_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
```

- **Idempotencia:** re-detectar el mismo faltante produce el mismo `gestion_id` → `POST` es no-op
  (o refresca metadata, ver §6).
- **URL-safe:** `gestion_id` es `g_` + 16 hex → seguro en `/v1/gestiones/{gestion_id}/...`.
- Se mantiene un **fixture compartido** (`tests/fixtures/gestion_id_contract.json`) con
  `{"input": {...}, "gestion_id_esperado": "g_..."}` que ambos repos deben pasar.

## 4. Lifecycle de estados

```
                POST /v1/gestiones
                       │
                       ▼
                  ┌──────────┐   personal marca hecha   ┌───────────┐
                  │ pendiente │ ───────────────────────▶ │ realizada │
                  └──────────┘   (UI granos)             └───────────┘
                                                          │        │
                              RPA verifica: dato presente │        │ RPA verifica: dato ausente
                                                          ▼        ▼
                                                   ┌───────────┐  ┌──────────────────────┐
                                                   │ verificada│  │ verificacion_fallida │
                                                   └───────────┘  └──────────────────────┘
                                                   (terminal)         │  personal corrige y re-marca
                                                                      └──────────▶ realizada
```

- `verificada` es **terminal**. Una gestión verificada no vuelve atrás.
- `verificacion_fallida` es la red de seguridad: el personal marcó hecha pero RPA no encontró el
  dato (ej.: lo cargaron en la empresa equivocada, o el alias no coincide). El personal corrige
  y re-marca `realizada`; RPA reintenta verificar en la próxima sincronización.

## 5. Auth, base URL, versionado

- Mismo mecanismo que la API existente: header **`X-API-Key`** con valor en `.env`
  (`LIQUIDADOR_API_KEY`). Sin header o inválido → `401`.
- Base URL: `http://<host>:8765/v1` (igual que los endpoints `/v1/coes/*`).
- Los endpoints viven bajo `/v1/gestiones` (conviven con `/v1/coes/*` y `/v2/*` sin cambios).
- `GET /v1/health` ya existe y no cambia.

## 6. Reglas transversales

- **Idempotencia del POST de creación:** la clave es `gestion_id`. Si ya existe, el `POST`
  **no cambia el estado**; solo refresca metadata mutable (`descripcion`, `datos_contexto`,
  `coes_afectados`, `detectado_en`) y devuelve `duplicado: true`. Nunca regresa el estado hacia atrás.
- **`coes_afectados`:** lista de COEs (14 díg.) que esta gestión está bloqueando. Sirve para que
  el personal priorice ("este alta destraba 8 liquidaciones"). RPA la manda y la **reemplaza
  completa** en cada POST (es la foto actual de qué liquidaciones dependen de esta gestión).
- **Timestamps:** ISO 8601 con TZ (ej. `2026-06-25T10:45:12-03:00`).
- **CUITs:** se transmiten normalizados a solo dígitos. El receptor no debe asumir guiones.

## 7. Códigos de error (todos los endpoints)

| HTTP | `error` | Cuándo |
|---|---|---|
| 401 | `api_key_invalida` | Header `X-API-Key` faltante o inválido. |
| 404 | `gestion_no_encontrada` | `gestion_id` no existe (en `/verificacion`). |
| 409 | `transicion_invalida` | Transición de estado no permitida (§4). Body incluye `estado_actual`. |
| 422 | `validacion_fallida` | Body/params mal formados (tipo fuera del enum, CUIT inválido, etc.). |
| 500 | `interno` | Error no controlado. |

---

# Parte B — Trabajo del lado granos.estudiobavera.com

> **Esta parte la implementa el agente de granos.** Es autocontenida: define el modelo de datos,
> los tres endpoints, la máquina de estados a enforcar, y la UI del personal. Lo de las Partes A y C
> es contexto, pero el contrato que DEBES cumplir está acá.

## 8. Implementación servidor + UI

### 8.1 Modelo de datos — tabla `gestiones`

```sql
CREATE TABLE gestiones (
    gestion_id       TEXT PRIMARY KEY,          -- 'g_' + 16 hex (§3), lo calcula y manda RPA
    tipo             TEXT NOT NULL,             -- alta_cliente | alta_proveedor | mapeo_grano | alta_cuenta
    cuit_empresa     TEXT NOT NULL,             -- solo dígitos
    razon_social     TEXT,                      -- nombre legible de la empresa (lo manda RPA)
    identificador    TEXT NOT NULL,             -- CUIT | cod_grano | alias, según tipo
    descripcion      TEXT NOT NULL,             -- texto humano listo para mostrar al personal
    datos_contexto   TEXT,                      -- JSON con campos extra de ayuda (§8.3)
    coes_afectados   TEXT,                      -- JSON array de COEs (14 díg.) bloqueados

    estado           TEXT NOT NULL,             -- pendiente | realizada | verificada | verificacion_fallida
    detectado_en     TEXT NOT NULL,             -- ISO 8601, lo manda RPA (primera detección)
    realizada_en     TEXT,                      -- ISO 8601, cuándo el personal marcó hecha
    realizada_por    TEXT,                      -- usuario del estudio que marcó (de la sesión web)
    verificada_en    TEXT,                      -- ISO 8601, cuándo RPA confirmó
    verificacion_detalle TEXT,                  -- mensaje opcional del resultado de verificación

    creado_en        TEXT NOT NULL,
    actualizado_en   TEXT NOT NULL
);

CREATE INDEX idx_gestiones_empresa_estado ON gestiones(cuit_empresa, estado);
CREATE INDEX idx_gestiones_estado ON gestiones(estado);
```

### 8.2 Máquina de estados (enforzar server-side)

Transiciones permitidas (cualquier otra → `409 transicion_invalida`):

| Desde | Hacia | Disparador |
|---|---|---|
| — | `pendiente` | `POST /v1/gestiones` (creación) |
| `pendiente` | `realizada` | UI personal |
| `verificacion_fallida` | `realizada` | UI personal |
| `realizada` | `verificada` | `POST /v1/gestiones/{id}/verificacion` (resultado=ok) |
| `realizada` | `verificacion_fallida` | `POST /v1/gestiones/{id}/verificacion` (resultado=fallida) |
| `verificada` | `verificada` | re-POST de creación → no-op idempotente |

### 8.3 `POST /v1/gestiones` — crear/refrescar gestiones (batch)

RPA lo llama al Importar. Recibe un **batch** (puede traer 0..N gestiones).

**Request:**

```jsonc
{
  "reportado_en": "2026-06-25T10:30:00-03:00",
  "gestiones": [
    {
      "gestion_id": "g_3f2a1b9c8d7e6f50",          // determinístico (§3) — la PK
      "tipo": "alta_cliente",
      "cuit_empresa": "30711165378",
      "razon_social": "Manassero Hnos SRL",
      "identificador": "30708729929",
      "descripcion": "Alta cliente CUIT 30708729929 en Manassero Hnos SRL",
      "datos_contexto": {                            // libre por tipo, ayuda al personal
        "cuit": "30708729929"
      },
      "coes_afectados": ["33023150836200", "33023150912345"],
      "detectado_en": "2026-06-25T10:30:00-03:00"
    },
    {
      "gestion_id": "g_aa11bb22cc33dd44",
      "tipo": "mapeo_grano",
      "cuit_empresa": "30711165378",
      "razon_social": "Manassero Hnos SRL",
      "identificador": "23",
      "descripcion": "Mapear grano Arca 23 (SOJA) a un ítem de stock agro en Manassero Hnos SRL",
      "datos_contexto": {
        "cod_grano_arca": "23",
        "nombre_grano_arca": "SOJA"
      },
      "coes_afectados": ["33013150700000"],
      "detectado_en": "2026-06-25T10:30:00-03:00"
    }
  ]
}
```

`datos_contexto` sugerido por tipo (campos orientativos, granos solo lo guarda y lo muestra):
- `alta_cliente` / `alta_proveedor`: `{ "cuit": "..." }`.
- `mapeo_grano`: `{ "cod_grano_arca": "23", "nombre_grano_arca": "SOJA" }`.
- `alta_cuenta`: `{ "alias": "RIVA", "para": "Retención IVA", "tipo_retencion": "RI06" }`.

**Comportamiento por gestión (idempotente, §6):**
- `gestion_id` **no existe** → INSERT con `estado='pendiente'`. Cuenta como `creada`.
- `gestion_id` **ya existe** → UPDATE de `descripcion`, `datos_contexto`, `coes_afectados`,
  `razon_social` (y `detectado_en` solo si está vacío). **No toca `estado`.** Cuenta como `actualizada`.

**Response 200:**

```jsonc
{
  "recibidas": 2,
  "creadas": 1,
  "actualizadas": 1,
  "resultados": [
    { "gestion_id": "g_3f2a1b9c8d7e6f50", "accion": "creada",      "duplicado": false },
    { "gestion_id": "g_aa11bb22cc33dd44", "accion": "actualizada", "duplicado": true  }
  ]
}
```

### 8.4 `GET /v1/gestiones` — listar estado

RPA lo llama al Sincronizar. El personal **no** usa este endpoint (usa la UI).

Query params (todos opcionales):

| Param | Tipo | Notas |
|---|---|---|
| `estado` | string repetible | Filtra por estado(s). Ej. `?estado=realizada`. Sin él → todas. |
| `cuit_empresa` | string repetible | Filtra por empresa(s). |
| `desde` | ISO date | `detectado_en >= desde`. |

**Response 200:**

```jsonc
{
  "total": 2,
  "gestiones": [
    {
      "gestion_id": "g_3f2a1b9c8d7e6f50",
      "tipo": "alta_cliente",
      "cuit_empresa": "30711165378",
      "razon_social": "Manassero Hnos SRL",
      "identificador": "30708729929",
      "descripcion": "Alta cliente CUIT 30708729929 en Manassero Hnos SRL",
      "datos_contexto": { "cuit": "30708729929" },
      "coes_afectados": ["33023150836200"],
      "estado": "realizada",
      "detectado_en": "2026-06-25T10:30:00-03:00",
      "realizada_en": "2026-06-25T14:05:00-03:00",
      "realizada_por": "ana.estudio",
      "verificada_en": null,
      "verificacion_detalle": null
    }
  ]
}
```

### 8.5 `POST /v1/gestiones/{gestion_id}/verificacion` — RPA confirma el resultado

RPA lo llama tras re-extraer y verificar. Solo válido si la gestión está en `realizada`.

**Request:**

```jsonc
{
  "resultado": "verificada",                  // "verificada" | "verificacion_fallida"
  "verificado_en": "2026-06-25T16:20:00-03:00",
  "detalle": "Cliente 30708729929 encontrado en SUSCRIP.DBF (cod 00000147)."  // opcional
}
```

**Comportamiento:**
- `resultado="verificada"` → `realizada → verificada`, set `verificada_en`, `verificacion_detalle`.
- `resultado="verificacion_fallida"` → `realizada → verificacion_fallida`, set `verificacion_detalle`.
- Si la gestión no está en `realizada` → `409 transicion_invalida` con `estado_actual`.
- Si `gestion_id` no existe → `404 gestion_no_encontrada`.

**Response 200:**

```jsonc
{ "gestion_id": "g_3f2a1b9c8d7e6f50", "estado": "verificada" }
```

### 8.6 UI del personal del estudio (granos web)

- **Vista "Gestiones de Holistor"**: lista filtrable por empresa y estado, ordenable por
  `detectado_en`. Cada fila muestra: empresa (`razon_social`), `descripcion`, tipo (con ícono/color),
  estado, y cantidad de COEs afectados (`len(coes_afectados)`) como señal de prioridad.
- **Acción por gestión**: botón "Marcar como hecha" (solo visible en `pendiente` y
  `verificacion_fallida`) → transición a `realizada`, set `realizada_en=now()` y
  `realizada_por=<usuario sesión>`.
- **Feedback de verificación**: las `verificada` se muestran resueltas (verde); las
  `verificacion_fallida` se destacan (rojo) con `verificacion_detalle` para que el personal
  entienda por qué no se encontró y corrija.
- **Agrupación sugerida**: por empresa, porque el personal trabaja una empresa a la vez en Holistor.

### 8.7 Criterios de aceptación (granos)

- [ ] Migración crea `gestiones` con índices.
- [ ] `POST /v1/gestiones` crea `pendiente` para `gestion_id` nuevo; refresca metadata sin tocar estado para existente; devuelve conteos correctos.
- [ ] `GET /v1/gestiones` filtra por `estado`/`cuit_empresa`/`desde` y devuelve el shape de §8.4.
- [ ] `POST /.../verificacion` aplica `realizada→verificada` / `realizada→verificacion_fallida`; rechaza desde otro estado con `409`.
- [ ] Endpoints sin `X-API-Key` → `401`.
- [ ] Transiciones inválidas → `409 transicion_invalida` con `estado_actual`.
- [ ] UI lista, filtra y permite marcar `realizada`; refleja `verificada`/`verificacion_fallida`.
- [ ] Endpoints `/v1/coes/*` y `/v2/*` existentes siguen intactos (regresión).

### 8.8 Tests sugeridos (granos)

- `test_post_gestiones_crea_pendiente`
- `test_post_gestiones_idempotente_refresca_metadata_no_estado`
- `test_post_gestiones_batch_mixto_creadas_y_actualizadas`
- `test_get_gestiones_filtra_por_estado_y_empresa`
- `test_post_verificacion_realizada_a_verificada`
- `test_post_verificacion_realizada_a_fallida`
- `test_post_verificacion_desde_pendiente_409`
- `test_verificacion_gestion_inexistente_404`
- `test_marcar_realizada_desde_fallida_ok`
- `test_endpoints_sin_apikey_401`
- `test_gestion_id_contract` (mismo fixture compartido que RPA)

---

# Parte C — Trabajo del lado rpa-holistor

## 9. Detector estructurado de faltantes

Refactor de `_validar_cuits_liquidacion` en [automation/phase_executors.py](../automation/phase_executors.py):

- Hoy devuelve `list[str]` (mensajes para el modal). Se introduce una función que devuelve
  **faltantes tipados**: `list[Faltante]`, donde `Faltante = {tipo, cuit_empresa, identificador,
  descripcion, datos_contexto}`.
- La función de strings actual queda como **capa fina** encima de la tipada (formatea cada
  `Faltante` a su mensaje corto), para no romper la pre-validación de Ejecutar ni el modal
  `CuitsInvalidosDialog`.
- Cobertura idéntica a la actual: empresa, cliente (`cuit_comprador`), proveedores (principal +
  de cada retención/deducción con importe>0), grano (`cod_grano`), y resolubilidad de
  tipo_retención/cuenta y tipo_movimiento/cuenta (→ `alta_cuenta` por alias no resoluble).

## 10. Cambios al ledger ([core/ledger.py](../core/ledger.py))

- **Nuevo estado `bloqueada`** en el `Literal` `Estado`. Semántica: importada pero no cargable
  hasta que se resuelvan sus gestiones.
- **Tabla `gestiones`** (espejo local; campos análogos a §8.1 más `sincronizado_api`,
  `sync_intentos`, `sync_ultimo_error`, mismo patrón que `coes_cargados`).
- **Tabla `liquidacion_gestiones`** (`coe`, `gestion_id`) — mapeo N↔N de qué gestiones bloquean
  qué liquidaciones.
- Helpers: `upsert_gestion`, `listar_gestiones`, `marcar_gestion_verificada/fallida`,
  `vincular_liquidacion_gestion`, `liquidaciones_bloqueadas_por`, `desbloquear_si_corresponde`.
- `calcular_gestion_id` (§3) vive acá, junto a `calcular_hash`.
- `listar_pendientes`/`listar` aceptan `bloqueada` en el filtro `estados`.

## 11. Cliente API ([core/api_client.py](../core/api_client.py)) — 3 métodos nuevos

- `reportar_gestiones(gestiones: list[dict]) -> ResultadoSync` → `POST /v1/gestiones` (con reintentos, mismo patrón que `reportar_cargado`).
- `obtener_gestiones(estado=None, cuits_empresa=None, desde=None) -> ResultadoSync` → `GET /v1/gestiones`.
- `confirmar_verificacion(gestion_id, resultado, detalle=None) -> ResultadoSync` → `POST /v1/gestiones/{id}/verificacion`.

## 12. Flujos y UI

### 12.1 Importar COEs (extiende [main.pyw](../main.pyw) `_importar_coes` + worker)

Tras el UPSERT de pendientes actual:
1. Sobre las liquidaciones **recién creadas**, correr el detector estructurado (§9).
2. Por cada faltante: `calcular_gestion_id`, `upsert_gestion` local (`pendiente`),
   `vincular_liquidacion_gestion`. Marcar la liquidación `bloqueada`.
3. Deduplicar gestiones (varias liqs → 1 gestión) y `reportar_gestiones` a granos en batch.
   Si la API falla, las gestiones quedan con `sincronizado_api=0` y se redrenan en el próximo Importar/Sync.
4. Toast extendido: "X nuevas · Z ignoradas · B bloqueadas · G gestiones reportadas".

### 12.2 Sincronizar gestiones (botón nuevo, **100% manual**)

1. `obtener_gestiones(estado="realizada")` desde granos.
2. Juntar las empresas + conjuntos involucrados (cliente→`SUSCRIP`, proveedor→`PROVEDOR`,
   grano→`STOCAGRO`, cuenta→`cuentas`).
3. **Re-extracción DIRIGIDA** desde `P:\` (solo esas empresas + esos conjuntos) — ver §12.3.
4. Re-correr el lookup de cada gestión `realizada`:
   - dato presente → `marcar_gestion_verificada` + `confirmar_verificacion(...,"verificada")`.
   - ausente → `marcar_gestion_fallida` + `confirmar_verificacion(...,"verificacion_fallida")`.
5. Para cada liquidación `bloqueada`: si **todas** sus gestiones quedaron `verificada` →
   `desbloquear_si_corresponde` la pasa a `pendiente`.
6. Toast: "V verificadas · F fallidas · D liquidaciones desbloqueadas".

> El operador dispara este flujo a mano. RPA **nunca** toca `P:\` sin ese click (respeta la
> cautela con producción del [CLAUDE.md](../CLAUDE.md)).

### 12.3 Extractores dirigidos

Agregar a [tools/extraer_clientes_proveedores_granos.py](../tools/extraer_clientes_proveedores_granos.py)
y [tools/extraer_cuentas_retenciones.py](../tools/extraer_cuentas_retenciones.py) un parámetro
`empresas: Optional[list[str]]` (filtro por alias) que:
- limite el sync de DBFs a esas empresas (menos exposición a `P:\`, más rápido);
- **mergee por-empresa** en el JSON existente (actualiza/agrega solo esas claves, preserva el resto),
  en vez de reescribir el archivo entero. Mantener el backup que ya hace `_backup_y_escribir`.

### 12.4 Modal Cargar ([ui/cargar_dialog.py](../ui/cargar_dialog.py))

- Incluir las `bloqueada` en el listado (junto a `pendiente`), con su motivo visible
  ("🔒 faltan N gestiones").
- Las filas `bloqueada` se muestran pero **no son seleccionables/tildables** para cargar.

## 13. Criterios de aceptación (rpa-holistor)

- [ ] Detector estructurado emite un `Faltante` tipado por cada dato ausente; la capa de strings
      preserva el comportamiento del modal de Ejecutar.
- [ ] `calcular_gestion_id` pasa el fixture compartido.
- [ ] Importar detecta faltantes, marca liquidaciones `bloqueada`, crea/vincula gestiones y las
      POSTea en batch (idempotente; redrena si la API estaba caída).
- [ ] Sincronizar lee `realizada`, re-extrae dirigido, verifica, confirma a granos y desbloquea
      liquidaciones cuyas gestiones quedaron todas `verificada`.
- [ ] Verificación fallida → `verificacion_fallida` reportada, liquidación sigue bloqueada.
- [ ] Modal Cargar muestra `bloqueada` no-tildables con motivo.
- [ ] Extractores dirigidos mergean por-empresa sin pisar las demás.

## 14. Tests (rpa-holistor)

- `test_detector_emite_faltante_por_tipo` (cliente/proveedor/grano/cuenta).
- `test_gestion_id_determinista_y_fixture_compartido`.
- `test_importar_marca_bloqueada_y_crea_gestiones`.
- `test_gestiones_dedup_varias_liqs_una_gestion`.
- `test_reportar_gestiones_redrena_si_api_caida`.
- `test_sync_verifica_y_desbloquea`.
- `test_sync_fallida_no_desbloquea`.
- `test_extractor_dirigido_mergea_por_empresa`.
- `test_cargar_dialog_muestra_bloqueada_no_tildable`.

## 15. Plan de implementación (orden sugerido)

**rpa-holistor:**
1. `calcular_gestion_id` + fixture compartido + ledger (estado `bloqueada`, tablas `gestiones`/`liquidacion_gestiones`, helpers).
2. Detector estructurado (refactor `_validar_cuits_liquidacion`).
3. Métodos del cliente API.
4. Worker Importar extendido (detección + bloqueo + reporte).
5. Extractores dirigidos (filtro por empresa + merge).
6. Worker + botón "Sincronizar gestiones" (GET + re-extract + verify + desbloqueo + confirmación).
7. Modal Cargar (mostrar `bloqueada` no-tildables).
8. Tests.

**granos.estudiobavera.com:** ver §8 (autocontenido). Integración end-to-end cuando ambos lados estén.

## 16. Fuera de scope (v1)

- Notificaciones push de granos → RPA (RPA pollea, no hay webhooks).
- Auto-disparo del Sincronizar (es manual a propósito).
- Detección de datos maestros que **cambiaron** (no que faltan) — ej. un CUIT que se editó en Holistor.
- Resolución automática de `alta_cuenta` creando la cuenta (siempre es alta manual del personal).
