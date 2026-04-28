# Contrato JSON v7 — Liquidaciones primarias de granos (RG 1116 AFIP)

**Audiencia:** agente de codificación que va a implementar, en el proyecto
`liquidador-granos`, la feature "exportar liquidaciones en JSON v7 consumible
por el RPA Holistor".

**Proyecto consumidor:** `rpa-holistor` (este repo). Este documento es
**autocontenido** — no hace falta leer el código del consumidor, solo cumplir
con lo que acá se define.

---

## 1. Contexto general (de qué se trata)

Un estudio contable usa **Holistor** (software contable en Visual FoxPro 7) para
imputar liquidaciones primarias de granos a cada una de sus empresas cliente.
El proceso manual por liquidación es tedioso: hay que abrir el form "Ventas
Agropecuario", tipear encabezado, cliente, proveedor, el grano con precio y
cantidad, retenciones y deducciones — todo celda por celda en grids de VFP.

Dos proyectos colaboran:

```
liquidador-granos (TU proyecto)              rpa-holistor (proyecto consumidor)
─────────────────────────────                ──────────────────────────────────
WebService LPG AFIP  ─────> JSON v7 ───────> Carga en Holistor vía pywinauto
(consulta las liquid.)       (archivo)       (automatización UI con UIA)
```

- **`liquidador-granos`** (el que vas a tocar): consume el WebService LPG de
  AFIP, normaliza los datos, aplica transformaciones de negocio, y **emite un
  archivo JSON v7** con N liquidaciones listas para ser importadas.
- **`rpa-holistor`**: lee ese JSON, valida, y carga cada liquidación en
  Holistor. No tiene acceso a AFIP ni conoce el LPG — solo confía en el JSON.

**Tu misión:** generar JSONs que cumplan el schema v7 exacto definido acá.
El RPA del otro lado ya funciona end-to-end con este contrato (F2→F13 verde).

---

## 2. El schema v7 — estructura raíz

Un archivo JSON v7 tiene un objeto raíz con **una sola key**: `"liquidaciones"`,
cuyo valor es una **lista** de 1 o más liquidaciones.

```jsonc
{
  "liquidaciones": [
    { /* liquidación 1 */ },
    { /* liquidación 2 */ },
    // ...
  ]
}
```

Cada liquidación en la lista es independiente. El RPA las procesa **una por
una** en orden.

---

## 3. Schema v7 — objeto liquidación

```jsonc
{
  // === Contexto (OBLIGATORIOS, excepto donde se indica) ===
  "cuit_empresa": "30711165378",         // CUIT de la empresa (cliente del estudio)
                                          //   string de 11 dígitos, sin guiones
  "mes": 2,                              // int 1..12 — mes de imputación
  "anio": 2026,                          // int — año de imputación
  "cuit_comprador": "30502874353",       // CUIT del comprador (cliente del form F7)
                                          //   obligatorio, 11 dígitos, sin guiones
  "cuit_proveedor": "30502874353",       // CUIT del proveedor (F7) — OPCIONAL
                                          //   omitir o "" si la liquidación no
                                          //   tiene retenciones ni deducciones

  // === Cabecera del comprobante (obligatorio) ===
  "comprobante": {
    "codigo": "F2",                      // "F1" | "F2" | "NL" (ver §4)
    "tipo_pto_vta": 3302,                // int — punto de venta AFIP (4 o 5 dígitos)
    "nro": 30384112,                     // int — número del comprobante
    "fecha_emision": "2026-02-26"        // string ISO "YYYY-MM-DD"
  },

  // === Datos del grano (obligatorio) ===
  "grano": {
    "cod_grano": 15,                     // int — código Arca del grano
    "precio_unitario": 205.6,            // float — $/TN (2 decimales)
    "cantidad_kg": 38193,                // int — cantidad en kg
    "neto_total": 7852593.91,            // float — base imponible
    "iva_monto": 824522.36,              // float — IVA calculado
    "subtotal": 8677116.27               // float — neto + iva
  },

  // === Retenciones (0..N) — OPCIONAL ===
  "retenciones": [
    {
      "codigo_arca": "RI",               // "RI" | "IB" | "RG" (ver §5)
      "importe": 628207.51,              // float
      "alicuota": 8.0,                   // float (%)
      "cuit_proveedor": "30502874353"    // 11 dígitos — del proveedor que retiene
    }
    // más ítems...
  ],

  // === Deducciones (0..N) — OPCIONAL ===
  "deducciones": [
    {
      "codigo_arca": "CO",               // código Arca (ver §6)
      "detalle": "Comision",             // string descriptivo
      "base": 95422.07,                  // float — base imponible
      "importe": 105441.39,              // float — base + iva (total)
      "alicuota_iva": 10.5,              // float (%). 0 = SIN IVA, >0 = CON IVA
      "importe_iva": 10019.32,           // float — IVA calculado
      "cuit_proveedor": "30506792165"    // 11 dígitos — prestador del servicio
    }
  ]
}
```

---

## 4. Campo `comprobante.codigo`

Alcance actual: **solo se soportan 3 tipos de comprobante**.

| `codigo` | Tipo AFIP | Descripción |
|---|---|---|
| `"F1"` | FC1116B | Factura de compra primaria |
| `"F2"` | FC1116C | Factura de compra primaria (tipo C) |
| `"NL"` | NCC1116 | Nota de crédito |

**⚠️ Importante:** el tipo de comprobante **NO sale del LPG** — lo decide el
operador humano antes de correr el RPA. En el flujo actual el JSON se genera
con `"codigo": "F2"` (default) y el usuario lo edita si corresponde otro.

**Sugerencia para el generador:** exponer un parámetro `default_codigo` (o dejar
el campo vacío `""` y que el RPA pida al usuario completar antes de arrancar).

---

## 5. Retenciones — códigos Arca aceptados

El campo `retenciones[].codigo_arca` corresponde al `codigoConcepto` del
WebService LPG de AFIP. Solo estos códigos llegan al JSON:

| `codigo_arca` | Significado Arca | Tratamiento en RPA |
|---|---|---|
| `"RI"` | Retención IVA | Se carga con tipo Holistor `RI06`, alias cuenta `RIVA` |
| `"IB"` | Retención IIBB (Origen + Destino **unificado**) | Tipo `PIBV`, alias `PIB` |
| `"RG"` | Retención Ganancias | Tipo `RG0X` (pendiente confirmar), alias `RGAN` |

### 🚨 Regla crítica: unificación IIBB

El WebService LPG emite **dos conceptos distintos para IIBB**:

- `"IB"` — IIBB **Origen** (provincia del vendedor).
- `"OG"` — IIBB **Destino** (provincia del comprador).

Desde el punto de vista contable del vendedor (que es quien carga la
liquidación), ambos se registran como **una sola retención IIBB unificada**.

**El generador DEBE sumar los importes de `IB` + `OG` y emitir un único
registro con `codigo_arca="IB"`**. El RPA rechaza silenciosamente `"OG"` si
llega (no debería llegar).

**Ejemplo:**

```
WebService LPG emite:
  { codigoConcepto: "IB", importeRetencion: 200000.00, alicuota: 4.0, ... }
  { codigoConcepto: "OG", importeRetencion: 127489.77, alicuota: 4.0, ... }

Generador debe emitir al JSON:
  { "codigo_arca": "IB", "importe": 327489.77, "alicuota": 8.0, ... }
                   ^^^^^           ^^^^^^^^^^              ^^^^
                   unificado        suma IB+OG         suma alícuotas
```

Si las alícuotas de IB y OG difieren, usá la suma (como en el ejemplo).

### Retenciones con importe 0

El RPA las skipea silenciosamente. No es error. Se pueden omitir del JSON, o
mantenerse — ambos comportamientos están soportados.

---

## 6. Deducciones — códigos Arca aceptados

El campo `deducciones[].codigo_arca` también viene del LPG. Los códigos
observados hasta ahora:

| `codigo_arca` | Descripción | `alicuota_iva` típica | Mapeo RPA |
|---|---|---|---|
| `"CO"` | Comisión | 10.5% | alias `COMI`, fallback `OGA` |
| `"OD"` | Impuesto Ley de Sellos | 0% | alias `OGA` |
| `"GS"` | Gastos varios / administrativos | 21% | alias `OGA` |
| _otros_ | (no mapeados) | — | fallback alias `OGA` (default) |

### Filtro CON IVA / SIN IVA

El RPA divide las deducciones en dos fases según el valor de `alicuota_iva`:

- **`alicuota_iva > 0`** → fase F12 (deducciones CON IVA).
- **`alicuota_iva == 0`** → fase F13 (deducciones SIN IVA).

**No hay overlap ni olvidos.** El filtro lo hace el RPA; el generador solo
tiene que emitir las deducciones con su `alicuota_iva` correcta.

### Cálculo de `importe` vs `base`

- **`base`**: monto sin IVA (base imponible).
- **`importe_iva`**: IVA calculado (`base × alicuota_iva / 100`).
- **`importe`**: total = `base + importe_iva`.

Para deducciones SIN IVA: `importe == base` y `importe_iva == 0`.

**El RPA verifica post-tipeo que `base × (1 + alicuota_iva/100) == importe`**
con tolerancia 0.05. Si difiere, aborta la fase — asegurate que la aritmética
del generador sea consistente.

### Fletes

El usuario reporta que los fletes **no aparecen como deducción** en el LPG de
granos — vienen descontados del precio unitario directamente. Si aparece algún
caso con flete como deducción, comunicar al equipo del RPA para agregar mapeo
específico (hoy existe un placeholder `_placeholder_FLETE` con alias `FYA`).

---

## 7. Proveedor de retenciones y deducciones

Cada ítem de `retenciones` y `deducciones` tiene su propio `cuit_proveedor`:

- **Retenciones:** generalmente es el mismo `cuit_proveedor` que el
  top-level del comprobante (el mismo proveedor retiene todo). **El RPA
  valida que el CUIT exista en el lookup de la empresa antes de arrancar.**
- **Deducciones:** puede diferir — p.ej. la comisión la cobra un corredor
  distinto, el impuesto de sellos lo paga otro proveedor. Cada una lleva su
  CUIT.

Si el CUIT del proveedor de una retención/deducción **no existe** en la base
Holistor de esa empresa, el RPA aborta en la pre-validación (F2) con error
claro. El generador no puede consultar los lookups del RPA, así que lo mejor
es **emitir el CUIT tal como viene del LPG** — el RPA hace la validación.

---

## 8. Caso especial: liquidación "mínima"

Si una liquidación NO tiene retenciones NI deducciones (solo grano), **no hay
proveedor**. El JSON debe omitir (o dejar vacías) las keys:

```jsonc
{
  "cuit_empresa": "30711165378",
  "mes": 2,
  "anio": 2026,
  "cuit_comprador": "30502874353",
  // "cuit_proveedor" OMITIDO (o "")
  "comprobante": { /* ... */ },
  "grano": { /* ... */ }
  // "retenciones" OMITIDO (o [])
  // "deducciones" OMITIDO (o [])
}
```

El RPA skipea F7-proveedor, F11, F12 y F13 silenciosamente.

---

## 9. Validaciones que el RPA hace al arrancar

El RPA corre una **pre-validación estricta** al leer el JSON (fase F2). Si
alguna falla, aborta antes de tocar Holistor y lista todos los problemas.
Qué chequea:

1. **`cuit_empresa`** existe en el maestro de empresas.
2. **`cuit_comprador`** existe en clientes de esa empresa.
3. **`cuit_proveedor`** (si se trae) existe en proveedores de esa empresa.
4. **`cod_grano`** mapea a un código de stock de la empresa.
5. Para cada retención con `importe > 0`:
   - `cuit_proveedor` de la retención existe en proveedores.
   - `codigo_arca` está en el mapeo (`RI`/`IB`/`RG`).
   - La cuenta con el alias correspondiente existe para esa empresa.
6. Para cada deducción con `importe > 0`:
   - `cuit_proveedor` existe en proveedores.
   - `codigo_arca` mapea a una cuenta (con fallback OGA).

**Consecuencia para el generador:** mandá los CUITs **tal como vienen del LPG**.
Si alguno no está cargado en la empresa destino en Holistor, es problema
operativo del estudio — el RPA lo señala claro.

---

## 10. Formatos y tipos

| Campo | Tipo Python/JSON | Formato / ejemplo |
|---|---|---|
| CUITs | `string` | `"30711165378"` (11 dígitos, sin guiones ni espacios) |
| `mes` | `int` | 1..12 (sin padding: `2`, no `"02"`) |
| `anio` | `int` | 4 dígitos (`2026`) |
| `comprobante.nro` | `int` | Sin separadores (`30384112`) |
| `comprobante.tipo_pto_vta` | `int` | Sin padding (`3302`) |
| `fecha_emision` | `string` ISO | `"2026-02-26"` (`YYYY-MM-DD`) |
| `cod_grano` | `int` | Código Arca numérico (`15`) |
| `precio_unitario` | `float` | 2 decimales, $/TN (`205.6`) |
| `cantidad_kg` | `int` | En kg, sin separadores (`38193`) |
| Todos los `importe`/`base`/`neto`/`iva`/`subtotal` | `float` | 2 decimales cuando corresponda, sin separadores |
| `alicuota`/`alicuota_iva` | `float` | Porcentaje sin símbolo `%` (`10.5`, no `"10.5%"`) |

**Encoding del archivo:** UTF-8 sin BOM. Uso de `ensure_ascii=False` en
`json.dumps` recomendado (detalles como "ñ" en razones sociales).

**Indentación:** 2 espacios para leibilidad; no es obligatorio (el RPA
acepta JSON minificado también).

---

## 11. Ejemplo completo (caso "rico")

Liquidación con 2 retenciones + 3 deducciones (CON IVA, CON IVA, SIN IVA):

```json
{
  "liquidaciones": [
    {
      "cuit_empresa": "30711165378",
      "mes": 2,
      "anio": 2026,
      "cuit_comprador": "30502874353",
      "cuit_proveedor": "30502874353",
      "comprobante": {
        "codigo": "F2",
        "tipo_pto_vta": 3302,
        "nro": 30384112,
        "fecha_emision": "2026-02-26"
      },
      "grano": {
        "cod_grano": 15,
        "precio_unitario": 205.6,
        "cantidad_kg": 38193,
        "neto_total": 7852593.91,
        "iva_monto": 824522.36,
        "subtotal": 8677116.27
      },
      "retenciones": [
        {
          "codigo_arca": "RI",
          "importe": 628207.51,
          "alicuota": 8.0,
          "cuit_proveedor": "30502874353"
        },
        {
          "codigo_arca": "IB",
          "importe": 327489.77,
          "alicuota": 8.0,
          "cuit_proveedor": "30502874353"
        }
      ],
      "deducciones": [
        {
          "codigo_arca": "CO",
          "detalle": "Comision",
          "base": 95422.07,
          "importe": 105441.39,
          "alicuota_iva": 10.5,
          "importe_iva": 10019.32,
          "cuit_proveedor": "30502874353"
        },
        {
          "codigo_arca": "GS",
          "detalle": "Gastos Varios",
          "base": 10000.00,
          "importe": 12100.00,
          "alicuota_iva": 21.0,
          "importe_iva": 2100.00,
          "cuit_proveedor": "30502874353"
        },
        {
          "codigo_arca": "OD",
          "detalle": "IMP LEY SELLOS",
          "base": 1889.36,
          "importe": 1889.36,
          "alicuota_iva": 0,
          "importe_iva": 0,
          "cuit_proveedor": "30502874353"
        }
      ]
    }
  ]
}
```

---

## 12. Ejemplo "mínimo" (solo grano, sin contrapartida en retenciones)

```json
{
  "liquidaciones": [
    {
      "cuit_empresa": "30711165378",
      "mes": 2,
      "anio": 2026,
      "cuit_comprador": "30502874353",
      "comprobante": {
        "codigo": "F2",
        "tipo_pto_vta": 3302,
        "nro": 30384113,
        "fecha_emision": "2026-02-26"
      },
      "grano": {
        "cod_grano": 15,
        "precio_unitario": 210.0,
        "cantidad_kg": 10000,
        "neto_total": 2100000.00,
        "iva_monto": 220500.00,
        "subtotal": 2320500.00
      }
    }
  ]
}
```

(Sin `cuit_proveedor`, sin `retenciones`, sin `deducciones`. El RPA lo acepta.)

---

## 13. Transformaciones que hace el generador vs el RPA

Para evitar duplicar lógica, dejamos claro qué responsabilidad tiene cada lado:

| Transformación | Responsable | Detalle |
|---|---|---|
| Consulta al WebService LPG AFIP | **Generador** | El RPA no toca AFIP |
| Unificar `OG` + `IB` → `IB` | **Generador** | El RPA rechaza `OG` |
| Limpiar CUITs (guiones/espacios) | RPA (defensivo) | Mejor mandar limpios desde el generador |
| Fecha ISO → int DDMMAAAA | **RPA** | El generador manda ISO, el RPA convierte |
| Código de comprobante (F1/F2/NL) | **Generador + operador** | Default, el operador edita si hace falta |
| Lookup de códigos Holistor (cuenta, grano, proveedor) | **RPA** | El generador no conoce Holistor |
| Validación de CUITs contra empresa | **RPA** (pre-validación F2) | El generador no conoce los lookups |
| Filtro CON/SIN IVA de deducciones | **RPA** (F12 vs F13) | El generador solo emite con `alicuota_iva` |

---

## 14. Checklist de implementación

Para el agente que va a escribir la feature en `liquidador-granos`:

- [ ] **Input:** respuesta del WebService LPG de AFIP (estructura JSON propia de
      AFIP, distinta del v7). Consumir `codigoConcepto`, `importeRetencion`,
      `alicuota`, `baseCalculo`, etc.
- [ ] **Normalizar CUITs** a 11 dígitos sin separadores (string).
- [ ] **Unificar IIBB**: detectar pares `IB`+`OG` del mismo proveedor y sumar
      importes + alícuotas en un único registro `IB`.
- [ ] **Construir objeto `grano`** con los montos del LPG (neto, IVA, subtotal).
      Verificar consistencia: `subtotal == neto + iva`.
- [ ] **Construir listas `retenciones` y `deducciones`** respetando schema v7.
      Incluir solo ítems con `importe > 0` (opcional — el RPA igual skipea los
      de importe 0).
- [ ] **Si la liquidación no tiene retenciones ni deducciones**, omitir
      `cuit_proveedor` top-level, `retenciones` y `deducciones` (o mandar
      vacíos).
- [ ] **`comprobante.codigo`**: elegir estrategia (default `"F2"`, o dejar `""`
      y obligar a que el operador lo complete antes de mandar al RPA).
- [ ] **Fecha**: emitir `fecha_emision` en formato ISO `"YYYY-MM-DD"`. El RPA la
      convierte internamente a DDMMAAAA.
- [ ] **Salida:** escribir archivo UTF-8 con el objeto raíz `{"liquidaciones":
      [...]}`. Un archivo puede tener N liquidaciones.
- [ ] **Tests mínimos que validen el output:**
  - Parsea como JSON válido.
  - Tiene la key `"liquidaciones"` y es lista.
  - Cada liquidación tiene `cuit_empresa`, `cuit_comprador`, `mes`, `anio`,
    `comprobante`, `grano`.
  - No hay ningún ítem con `codigo_arca == "OG"` (debe estar fusionado).
  - Los CUITs son strings de 11 dígitos sin caracteres no-numéricos.
  - Para cada deducción CON IVA: `base × (1 + alicuota_iva/100) ≈ importe`
    (tolerancia 0.05).

---

## 15. Evolución del contrato

Este schema es la **versión 7** del contrato (v1–v6 fueron formatos Excel que
quedaron deprecated). Cualquier cambio al schema:

1. Debe ser acordado entre los dos proyectos antes de implementarse.
2. Se documenta en este archivo + en el `CLAUDE.md` de `rpa-holistor`.
3. Idealmente con retrocompatibilidad: el RPA acepta v7 y v7.1, etc.
4. Si se rompe retrocompat, se sube a v8 y hay un período de migración.

### Cambios no-compatibles que requieren v8

- Cambiar el nombre de la key raíz.
- Cambiar tipos de campos existentes.
- Mover campos entre nesting levels.
- Agregar un nuevo campo obligatorio.

### Cambios compatibles (quedan en v7.x)

- Agregar un campo opcional nuevo.
- Nuevos códigos Arca en la tabla de mapeo.
- Nuevos tipos de comprobante.

---

## 16. Contacto / dudas

Si aparece un caso del LPG que este documento no cubre (ej. deducción con un
`codigoConcepto` nuevo, retención con estructura distinta, liquidación con
múltiples granos en un mismo comprobante), **no inventar** — consultar con el
equipo del RPA antes de generar el JSON, porque el RPA puede necesitar cambios
paralelos.

El changelog y estado actual del RPA viven en:
- `docs/changelog_YYYY-MM-DD.md` — histórico de cambios.
- `CLAUDE.md` — documento de contexto del RPA (incluye este contrato en forma
  resumida).
