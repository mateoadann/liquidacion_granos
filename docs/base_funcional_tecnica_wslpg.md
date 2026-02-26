# Herramienta de Control / Extracción y Gestión de Liquidación Primaria de Granos (LPG)

**Estado:** Borrador inicial (v0.1)  
**Fecha:** 2026-02-25  
**Proyecto:** /Users/mateo/Documents/clientes/liquidacion_granos

---

## 1) Objetivo del sistema

Construir una aplicación con interfaz gráfica para:

1. Extraer información de LPG por productor/CUIT representada.
2. Consultar, auditar y gestionar estados/documentos de LPG (y relacionados).
3. Integrar con ARCA/AFIP vía web services, usando la librería `arca_arg` como capa de conexión Python.

---

## 2) Funcionamiento y requerimientos (base funcional)

### 2.1 Flujo funcional principal

1. **Alta de contribuyente representado** (CUIT, certificados, ambiente).
2. **Autenticación/Autorización** (WSAA → token/sign).
3. **Chequeo operativo del servicio** (`dummy`).
4. **Sincronización de catálogos** (granos, campañas, puertos, actividades, etc.).
5. **Extracción/consulta** (por COE, nro orden, contrato, incremental por último nro orden).
6. **Gestión operativa** (autorizar, ajustar, anular/contra-documento, anticipos).
7. **Auditoría y monitoreo** (errores formato, errores negocio, eventos, trazabilidad XML).

### 2.2 Requerimientos funcionales iniciales

- Multi-CUIT y multi-productor.
- Ejecución manual y programada de extracciones.
- Persistencia de requests/responses y estados.
- Recuperación ante timeout/cortes de comunicación.
- Manejo de errores por canal:
  - SOAP Fault (excepcionales)
  - `erroresFormato`
  - `errores` negocio/infraestructura
- Exportación de resultados (JSON/CSV; PDF cuando el método lo permita).

### 2.3 Requerimientos no funcionales

- Seguridad de secretos (cert/key/token).
- Idempotencia por CUIT + punto emisión + nro orden + operación.
- Logs estructurados y métricas.
- Reintentos con backoff para fallas de infraestructura.
- Trazabilidad fiscal completa.

---

## 3) Métodos detectados en documentación WSLPG v1.24

> Fuente: manual local `manual_wslpg_1.24.pdf` (30/01/2026)

### 3.1 Generales

- `dummy`

### 3.2 LPG primaria / ajustes / consultas

- `liquidacionAutorizar`
- `liquidacionAjustarUnificado`
- `liquidacionAjustarContrato`
- `asociarLiquidacionAContrato`
- `liquidacionAnular` *(histórico; en cambios de versión figura discontinuado en favor de contra-documento)*
- `liquidacionXNroOrdenConsultar`
- `liquidacionXCoeConsultar`
- `ajusteXCoeConsultar`
- `ajustePorContratoConsultar`
- `ajusteXNroOrdenConsultar`
- `liquidacionPorContratoConsultar`
- `liquidacionUltimoNroOrdenConsultar`
- `lpgAnularContraDocumento`

### 3.3 Maestros / tablas auxiliares

- `campaniasConsultar`
- `tipoGranoConsultar`
- `codigoGradoReferenciaConsultar`
- `codigoGradoEntregadoXTipoGranoConsultar`
- `tipoCertificadoDepositoConsultar`
- `tipoDeduccionConsultar`
- `tipoRetencionConsultar`
- `puertoConsultar`
- `tipoActividadConsultar`
- `tipoActividadRepresentadoConsultar`
- `provinciasConsultar`
- `localidadXProvinciaConsultar`
- `tipoOperacionXActividadConsultar`

### 3.4 LSG (liquidación secundaria)

- `lsgAutorizar`
- `lsgConsultarXCoe`
- `lsgConsultarXNroOrden`
- `lsgConsultarUltimoNroOrden`
- `lsgAnular` *(histórico; changelog indica reemplazo por `lsgAnularContraDocumento`)*
- `lsgAjustarXCoe`
- `lsgAjustarXContrato`
- `lsgAsociarAContrato`
- `lsgConsultarXContrato`

### 3.5 Certificación de granos (CG)

- `cgAutorizar`
- `cgBuscarCtg`
- `cgBuscarCertConSaldoDisponible`
- `cgConsultarUltimoNroOrden`
- `cgSolicitarAnulacion`
- `cgConfirmarAnulacion`
- `cgConsultarXCoe`
- `cgConsultarXNroOrden`
- `cgInformarCalidad`

### 3.6 Anticipos LPG

- `lpgAutorizarAnticipo`
- `lpgCancelarAnticipo`

---

## 4) Qué ofrece la librería `arca_arg` (repositorio + blog)

### 4.1 Servicios y endpoints configurables

En `settings.py` aparecen:

- `WS_LIST` (incluye `wslpg`)
- `WSDL_LPG_HOM = https://fwshomo.afip.gov.ar/wslpg/LpgService?wsdl`
- `WSDL_LPG_PROD = https://serviciosjava.afip.gob.ar/wslpg/LpgService?wsdl`

### 4.2 API principal expuesta por `ArcaWebService`

- `send_request(method_name, data, ...)`
- `list_methods()`
- `method_help(method_name)`
- `get_type(type_name)`
- `create_message(method_name, data)`
- `dump_wsdl()`

### 4.3 Conclusión técnica sobre `arca_arg`

`arca_arg` funciona como cliente SOAP genérico + autenticación; no está limitado a un set fijo de métodos de LPG.  
Permite:

1. Inicializar contra WSDL de WSLPG.
2. Descubrir métodos reales del servicio (`list_methods`).
3. Inspeccionar firma y tipos (`method_help` / `get_type`).
4. Enviar solicitudes con `send_request`.

---

## 5) Tipos de solicitudes que podremos implementar

### 5.1 Solicitudes de consulta/extracción

- Consulta por COE.
- Consulta por punto emisión + nro orden.
- Consulta incremental por último nro orden.
- Consulta por contrato.
- Descarga de PDF (métodos que soportan `pdf = S`).

### 5.2 Solicitudes de operación

- Autorizar LPG.
- Ajustes (unificado/contrato/COE según método).
- Anulación por contra-documento.
- Gestión de anticipos (alta/cancelación).

### 5.3 Solicitudes de sincronización de catálogos

- Granos, campañas, puertos, actividades, deducciones, retenciones, provincias/localidades, etc.

### 5.4 Solicitudes de control

- `dummy` para salud del servicio.
- Auditoría de errores/eventos por operación.

---

## 6) Stack tecnológico propuesto (aceptado)

### Frontend

- React 18
- Vite
- TanStack Query
- Zustand
- Tailwind CSS

### Backend

- Flask 3
- SQLAlchemy 2
- Redis
- PostgreSQL 16

### Integración ARCA

- Librería `arca_arg` para conexión a WSLPG

### Arquitectura sugerida (alto nivel)

- **frontend/**: UI de extracciones, resultados, detalle de errores, configuración CUIT.
- **backend/api/**: endpoints REST internos.
- **backend/workers/**: jobs asíncronos (colas Redis) para extracciones y sync de catálogos.
- **backend/integrations/arca/**: adaptadores `arca_arg` + mapeos request/response.
- **backend/db/**: modelos SQLAlchemy + migraciones.

---

## 7) Próximos pasos inmediatos

1. Ejecutar discovery real de métodos WSLPG en homologación con `arca_arg.list_methods()`.
2. Crear matriz de operaciones (método, request type, response type, errores esperados).
3. Definir esquema de datos inicial (contribuyente, job, documento, evento_error, auditoría_xml).
4. Generar scaffold base del stack (frontend + backend + docker compose con postgres/redis).

---

## 8) Fuentes

- Manual local: `/Users/mateo/Documents/clientes/liquidacion_granos/manual_wslpg_1.24.pdf`
- Blog ARCA Arg: https://relopezbriega.github.io/blog/2025/01/27/libreria-arca-arg-conectando-tu-aplicacion-con-los-servicios-web-de-arca-afip-con-python/
- Repositorio ARCA Arg: https://github.com/relopezbriega/arca_arg
- `arca_arg/settings.py` (raw): https://raw.githubusercontent.com/relopezbriega/arca_arg/main/arca_arg/settings.py
- `arca_arg/webservice.py` (raw): https://raw.githubusercontent.com/relopezbriega/arca_arg/main/arca_arg/webservice.py
- PyPI arca-arg: https://pypi.org/project/arca-arg/

---

## 9) Tipos de request detectados en el manual (wrappers `*Req`)

> Relevados automáticamente del texto del manual. Sirven para mapear cada operación SOAP con su payload raíz.

- `CgConsultarXNroOrdenReq`
- `CgInformarCalidadReq`
- `LpgAnularContraDocumentoReq`
- `LpgAutorizarAnticipoReq`
- `LpgCancelarAnticipoReq`
- `ajustarContratoReq`
- `ajustarUnificadoReq`
- `ajustePorContratoConsultarReq`
- `ajusteXCoeConsReq`
- `ajusteXNroOrdenConsReq`
- `anulacionReq`
- `asociarLiqAContratoReq`
- `campaniaReq`
- `cgAutorizarReq`
- `cgBuscarCertConSaldoDisponibleReq`
- `cgBuscarCtgReq`
- `cgConfirmarAnulacionReq`
- `cgConsultarUltimoNroOrdenReq`
- `cgConsultarXCoeReq`
- `cgConsultarXNroOrdenReq`
- `cgSolicitarAnulacionReq`
- `gradoEntregadoReq`
- `gradoReferenciaReq`
- `liqConsXCoeReq`
- `liqConsXNroOrdenReq`
- `liqUltNroOrdenReq`
- `liquidacionPorContratoConsultarReq`
- `liquidacionReq`
- `localidadReq`
- `lsgAjustarXCoeReq`
- `lsgAjustarXContratoReq`
- `lsgAnularReq`
- `lsgAsociarAContratoReq`
- `lsgAutorizarReq`
- `lsgCancelarAnticipoReq` *(inconsistencia aparente de nombre en manual)*
- `lsgConsultarUltimoNroOrdenReq`
- `lsgConsultarXCoeReq`
- `lsgConsultarXContratoReq`
- `lsgConsultarXNroOrdenReq`
- `provinciasReq`
- `puertoReq`
- `tipoActividadRepresentadoReq`
- `tipoActividadReq`
- `tipoCertificadoDepReq`
- `tipoDeduccionReq`
- `tipoGranoReq`
- `tipoOperacionReq`
- `tipoRetencionReq`

---

## 10) Avance técnico implementado (2026-02-25)

Se implementó el bloque base de backend para continuar con desarrollo:

- Migraciones con **Flask-Migrate/Alembic** (`/backend/migrations`).
- API de contribuyentes:
  - `GET /api/taxpayers`
  - `POST /api/taxpayers`
  - `GET /api/taxpayers/<id>`
  - `PATCH /api/taxpayers/<id>`
- API de jobs de extracción:
  - `GET /api/jobs`
  - `POST /api/jobs`
  - `GET /api/jobs/<id>`
  - `PATCH /api/jobs/<id>`
- Discovery real de métodos WSLPG vía `arca_arg`:
  - `GET /api/discovery/wslpg/methods`
  - `GET /api/discovery/wslpg/methods/<method_name>`
  - script: `/backend/scripts_discover_wslpg.py`

Ajustes de infraestructura:

- Backend operativo en **puerto 5001**.
- Frontend apuntando por defecto a `http://localhost:5001/api`.

- API MVP WSLPG implementada en backend y disponible desde frontend simple para los métodos:
  - `dummy`
  - `liquidacionUltimoNroOrdenConsultar`
  - `liquidacionXNroOrdenConsultar`
  - `liquidacionXCoeConsultar`
