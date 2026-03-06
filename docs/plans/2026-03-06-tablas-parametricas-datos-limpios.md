# Tablas Parametricas y Datos Limpios - Plan de Implementacion

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Sincronizar tablas parametricas del web service WSLPG (granos, grados, puertos, provincias, localidades, deducciones, retenciones) y generar un campo `datos_limpios` en cada LpgDocument que contenga los datos del raw_data enriquecidos con descripciones legibles. El frontend y la exportacion consumen `datos_limpios`.

**Architecture:** Un modelo `WslpgParameterTable` almacena todos los catalogos con esquema (tabla, codigo, descripcion). Un servicio `ParameterSyncService` llama a los metodos SOAP de consulta de maestros y guarda/actualiza los registros. Un servicio `DatosLimpiosBuilder` toma el `raw_data` de un LpgDocument y lo transforma en un dict plano enriquecido con descripciones, guardandolo en `datos_limpios`. Un endpoint admin permite ejecutar la sincronizacion de parametros y el reprocesamiento masivo de datos limpios.

**Tech Stack:** Flask, SQLAlchemy, Alembic, arca_arg (SOAP), pytest

---

## Contexto critico

### Estructura de raw_data

El campo `raw_data` en LpgDocument se guarda como `{"data": {...respuesta_soap...}}`. La respuesta SOAP se serializa con `zeep.helpers.serialize_object` y se normaliza con `_normalize_json_safe`. Los campos de la liquidacion estan DENTRO de `raw_data["data"]`, posiblemente anidados en sub-dicts.

### Metodos SOAP disponibles para maestros (seccion 3.3 del doc)

Todos requieren `auth` payload (token + sign + cuit):

| Metodo SOAP | Que devuelve | Request type |
|---|---|---|
| `tipoGranoConsultar` | Lista de granos (cod + descripcion) | `tipoGranoReq` |
| `codigoGradoReferenciaConsultar` | Grados de referencia | `gradoReferenciaReq` |
| `codigoGradoEntregadoXTipoGranoConsultar` | Grados entregados por tipo grano | `gradoEntregadoReq` |
| `tipoDeduccionConsultar` | Tipos de deduccion | `tipoDeduccionReq` |
| `tipoRetencionConsultar` | Tipos de retencion | `tipoRetencionReq` |
| `puertoConsultar` | Puertos | `puertoReq` |
| `provinciasConsultar` | Provincias | `provinciasReq` |
| `localidadXProvinciaConsultar` | Localidades por provincia | `localidadReq` |
| `tipoOperacionXActividadConsultar` | Tipos de operacion | `tipoOperacionReq` |
| `campaniasConsultar` | Campanias | `campaniaReq` |

### Claves que necesitamos resolver

| Campo en raw_data | Tabla parametrica |
|---|---|
| `codGrano` | tipoGrano |
| `codGradoRef` | gradoReferencia |
| `codGradoEnt` | gradoEntregado |
| `codPuerto` | puerto |
| `codProvProcedencia` | provincia |
| `codLocalidadProcedencia` + `codProvProcedencia` | localidad |
| `codTipoOperacion` | tipoOperacion |
| deducciones[].codigoConcepto | tipoDeduccion |
| retenciones[].codigoConcepto | tipoRetencion |

---

## Task 1: Modelo WslpgParameterTable + Migracion

**Files:**
- Create: `backend/app/models/wslpg_parameter.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/20260306_0004_wslpg_parameters.py`
- Test: `backend/tests/unit/test_wslpg_parameter_model.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/test_wslpg_parameter_model.py
from __future__ import annotations

from app.extensions import db
from app.models import WslpgParameter


def test_create_parameter(app):
    with app.app_context():
        param = WslpgParameter()
        param.tabla = "tipoGrano"
        param.codigo = "15"
        param.descripcion = "TRIGO PAN"
        param.datos_extra = {"vigente": True}
        db.session.add(param)
        db.session.commit()

        found = WslpgParameter.query.filter_by(tabla="tipoGrano", codigo="15").first()
        assert found is not None
        assert found.descripcion == "TRIGO PAN"
        assert found.datos_extra["vigente"] is True


def test_unique_constraint(app):
    import pytest
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        p1 = WslpgParameter(tabla="tipoGrano", codigo="15", descripcion="TRIGO PAN")
        db.session.add(p1)
        db.session.commit()

        p2 = WslpgParameter(tabla="tipoGrano", codigo="15", descripcion="DUPLICADO")
        db.session.add(p2)
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_lookup_helper(app):
    with app.app_context():
        p = WslpgParameter(tabla="puerto", codigo="14", descripcion="OTROS")
        db.session.add(p)
        db.session.commit()

        desc = WslpgParameter.lookup("puerto", "14")
        assert desc == "OTROS"

        missing = WslpgParameter.lookup("puerto", "999")
        assert missing is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/unit/test_wslpg_parameter_model.py -v`
Expected: FAIL — ImportError WslpgParameter not found

**Step 3: Write model**

```python
# backend/app/models/wslpg_parameter.py
from __future__ import annotations

from ..extensions import db
from ..time_utils import now_cordoba_naive


class WslpgParameter(db.Model):
    """Tabla parametrica sincronizada desde WSLPG (granos, puertos, etc)."""

    __tablename__ = "wslpg_parameter"
    __table_args__ = (
        db.UniqueConstraint("tabla", "codigo", name="uq_wslpg_param_tabla_codigo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tabla = db.Column(db.String(60), nullable=False, index=True)
    codigo = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.String(255), nullable=False, default="")
    datos_extra = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cordoba_naive, onupdate=now_cordoba_naive)

    @classmethod
    def lookup(cls, tabla: str, codigo: str | int) -> str | None:
        row = cls.query.filter_by(tabla=tabla, codigo=str(codigo)).first()
        return row.descripcion if row else None

    @classmethod
    def lookup_map(cls, tabla: str) -> dict[str, str]:
        rows = cls.query.filter_by(tabla=tabla).all()
        return {row.codigo: row.descripcion for row in rows}
```

Update `backend/app/models/__init__.py`:
```python
from .wslpg_parameter import WslpgParameter
# agregar a __all__
```

**Step 4: Write migration**

```python
# backend/migrations/versions/20260306_0004_wslpg_parameters.py
"""Add wslpg_parameter table

Revision ID: 20260306_0004
Revises: 4029dab0d551
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = "20260306_0004"
down_revision = "4029dab0d551"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wslpg_parameter",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tabla", sa.String(60), nullable=False, index=True),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("descripcion", sa.String(255), nullable=False, server_default=""),
        sa.Column("datos_extra", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tabla", "codigo", name="uq_wslpg_param_tabla_codigo"),
    )


def downgrade():
    op.drop_table("wslpg_parameter")
```

**Step 5: Run tests to verify pass**

Run: `cd backend && python3 -m pytest tests/unit/test_wslpg_parameter_model.py -v`
Expected: 3 PASSED

**Step 6: Commit**

```bash
git add backend/app/models/wslpg_parameter.py backend/app/models/__init__.py \
  backend/migrations/versions/20260306_0004_wslpg_parameters.py \
  backend/tests/unit/test_wslpg_parameter_model.py
git commit -m "feat: add WslpgParameter model for parametric tables"
```

---

## Task 2: ParameterSyncService - Sincronizar tablas desde WSLPG

**Files:**
- Create: `backend/app/services/parameter_sync.py`
- Modify: `backend/app/services/__init__.py` (si exporta services)
- Test: `backend/tests/unit/test_parameter_sync.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/test_parameter_sync.py
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import WslpgParameter
from app.services.parameter_sync import ParameterSyncService


def _mock_ws_client():
    """Crea un mock de ArcaWslpgClient que devuelve datos simulados."""
    client = MagicMock()

    # tipoGranoConsultar
    client.send_request.side_effect = _route_mock_request
    client.get_auth_payload.return_value = {"token": "t", "sign": "s", "cuit": 1}
    client.connect.return_value = client
    return client


def _route_mock_request(method_name, data):
    """Simula respuestas SOAP por metodo."""
    responses = {
        "tipoGranoConsultar": {
            "tipoGrano": [
                {"codTipoGrano": 15, "descTipoGrano": "TRIGO PAN"},
                {"codTipoGrano": 2, "descTipoGrano": "MAIZ"},
            ]
        },
        "puertoConsultar": {
            "puerto": [
                {"codPuerto": 14, "desPuerto": "OTROS"},
            ]
        },
        "provinciasConsultar": {
            "provincia": [
                {"codProvincia": 3, "desProvincia": "CORDOBA"},
            ]
        },
        "tipoDeduccionConsultar": {
            "tipoDeduccion": [
                {"codigoConcepto": "OD", "descripcionConcepto": "Otras Deducciones"},
                {"codigoConcepto": "GA", "descripcionConcepto": "Comision o Gastos Administrativos"},
            ]
        },
        "tipoRetencionConsultar": {
            "tipoRetencion": [
                {"codigoConcepto": "RG", "descripcionConcepto": "Retencion Ganancias"},
                {"codigoConcepto": "RI", "descripcionConcepto": "Retencion IVA"},
            ]
        },
        "codigoGradoReferenciaConsultar": {
            "gradoRef": [
                {"codGradoRef": "G2", "descGradoRef": "Grado 2"},
            ]
        },
        "codigoGradoEntregadoXTipoGranoConsultar": {
            "gradoEnt": [
                {"codGradoEnt": "G2", "descGradoEnt": "Grado 2"},
            ]
        },
        "localidadXProvinciaConsultar": {
            "localidad": [
                {"codLocalidad": 1443, "descLocalidad": "BENGOLEA"},
            ]
        },
        "tipoOperacionXActividadConsultar": {
            "tipoOperacion": [
                {"codTipoOperacion": 1, "descTipoOperacion": "Compraventa"},
                {"codTipoOperacion": 2, "descTipoOperacion": "Consignacion"},
            ]
        },
    }
    return responses.get(method_name, {})


def test_sync_granos(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_tipo_grano()

        assert result["synced"] == 2
        assert WslpgParameter.lookup("tipoGrano", "15") == "TRIGO PAN"
        assert WslpgParameter.lookup("tipoGrano", "2") == "MAIZ"


def test_sync_puertos(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_puertos()

        assert result["synced"] == 1
        assert WslpgParameter.lookup("puerto", "14") == "OTROS"


def test_sync_deducciones(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_tipo_deduccion()

        assert result["synced"] == 2
        assert WslpgParameter.lookup("tipoDeduccion", "OD") == "Otras Deducciones"


def test_sync_retenciones(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        result = service.sync_tipo_retencion()

        assert result["synced"] == 2
        assert WslpgParameter.lookup("tipoRetencion", "RG") == "Retencion Ganancias"


def test_sync_all(app):
    with app.app_context():
        service = ParameterSyncService(_mock_ws_client())
        results = service.sync_all()

        assert "tipoGrano" in results
        assert "puerto" in results
        assert "provincia" in results
        assert "tipoDeduccion" in results
        assert "tipoRetencion" in results


def test_sync_upserts_on_duplicate(app):
    with app.app_context():
        # Primera sync
        service = ParameterSyncService(_mock_ws_client())
        service.sync_tipo_grano()

        # Verificar valor inicial
        assert WslpgParameter.lookup("tipoGrano", "15") == "TRIGO PAN"

        # Segunda sync con mismo mock — debe upsert sin error
        service.sync_tipo_grano()
        assert WslpgParameter.lookup("tipoGrano", "15") == "TRIGO PAN"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/unit/test_parameter_sync.py -v`
Expected: FAIL — ImportError

**Step 3: Write ParameterSyncService**

```python
# backend/app/services/parameter_sync.py
from __future__ import annotations

import logging
from typing import Any

from ..extensions import db
from ..models import WslpgParameter

logger = logging.getLogger(__name__)


class ParameterSyncService:
    """Sincroniza tablas parametricas del WSLPG a la BD local."""

    def __init__(self, ws_client: Any):
        self._ws = ws_client

    # ------------------------------------------------------------------
    # Upsert generico
    # ------------------------------------------------------------------
    def _upsert_rows(self, tabla: str, rows: list[dict[str, Any]], cod_key: str, desc_key: str) -> dict:
        synced = 0
        for row in rows:
            codigo = str(row.get(cod_key, ""))
            descripcion = str(row.get(desc_key, ""))
            if not codigo:
                continue

            existing = WslpgParameter.query.filter_by(tabla=tabla, codigo=codigo).first()
            if existing:
                existing.descripcion = descripcion
                existing.datos_extra = row
            else:
                param = WslpgParameter(
                    tabla=tabla, codigo=codigo, descripcion=descripcion, datos_extra=row,
                )
                db.session.add(param)
            synced += 1

        db.session.commit()
        logger.info("PARAM_SYNC | tabla=%s synced=%d", tabla, synced)
        return {"tabla": tabla, "synced": synced}

    def _call(self, method: str, extra_data: dict | None = None) -> Any:
        data = {"auth": self._ws.get_auth_payload()}
        if extra_data:
            data.update(extra_data)
        result = self._ws.send_request(method, data)
        # Respuesta puede venir serializada con {"data": ...} o directamente
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result

    # ------------------------------------------------------------------
    # Metodos de sync individuales
    # ------------------------------------------------------------------
    def sync_tipo_grano(self) -> dict:
        data = self._call("tipoGranoConsultar")
        rows = data.get("tipoGrano", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("tipoGrano", rows, "codTipoGrano", "descTipoGrano")

    def sync_grado_referencia(self) -> dict:
        data = self._call("codigoGradoReferenciaConsultar")
        rows = data.get("gradoRef", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("gradoReferencia", rows, "codGradoRef", "descGradoRef")

    def sync_grado_entregado(self) -> dict:
        data = self._call("codigoGradoEntregadoXTipoGranoConsultar")
        rows = data.get("gradoEnt", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("gradoEntregado", rows, "codGradoEnt", "descGradoEnt")

    def sync_puertos(self) -> dict:
        data = self._call("puertoConsultar")
        rows = data.get("puerto", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("puerto", rows, "codPuerto", "desPuerto")

    def sync_provincias(self) -> dict:
        data = self._call("provinciasConsultar")
        rows = data.get("provincia", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("provincia", rows, "codProvincia", "desProvincia")

    def sync_localidades(self, cod_provincia: int | None = None) -> dict:
        """Sincroniza localidades. Si cod_provincia es None, sincroniza para TODAS las provincias ya sincronizadas."""
        if cod_provincia is not None:
            return self._sync_localidades_provincia(cod_provincia)

        provincias = WslpgParameter.query.filter_by(tabla="provincia").all()
        total = 0
        for prov in provincias:
            try:
                result = self._sync_localidades_provincia(int(prov.codigo))
                total += result["synced"]
            except Exception as exc:
                logger.warning("PARAM_SYNC_LOCALIDAD_ERROR | provincia=%s error=%s", prov.codigo, exc)
        return {"tabla": "localidad", "synced": total}

    def _sync_localidades_provincia(self, cod_provincia: int) -> dict:
        data = self._call("localidadXProvinciaConsultar", {"codProvincia": cod_provincia})
        rows = data.get("localidad", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        # Prefijamos el codigo con la provincia para unicidad: "3_1443"
        enriched = []
        for row in rows:
            row_copy = dict(row)
            row_copy["_cod_compuesto"] = f"{cod_provincia}_{row.get('codLocalidad', '')}"
            row_copy["_desc_localidad"] = str(row.get("descLocalidad", ""))
            enriched.append(row_copy)
        return self._upsert_rows("localidad", enriched, "_cod_compuesto", "_desc_localidad")

    def sync_tipo_deduccion(self) -> dict:
        data = self._call("tipoDeduccionConsultar")
        rows = data.get("tipoDeduccion", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("tipoDeduccion", rows, "codigoConcepto", "descripcionConcepto")

    def sync_tipo_retencion(self) -> dict:
        data = self._call("tipoRetencionConsultar")
        rows = data.get("tipoRetencion", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("tipoRetencion", rows, "codigoConcepto", "descripcionConcepto")

    def sync_tipo_operacion(self) -> dict:
        data = self._call("tipoOperacionXActividadConsultar")
        rows = data.get("tipoOperacion", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = [rows]
        return self._upsert_rows("tipoOperacion", rows, "codTipoOperacion", "descTipoOperacion")

    # ------------------------------------------------------------------
    # Sync all
    # ------------------------------------------------------------------
    def sync_all(self) -> dict[str, dict]:
        results = {}
        methods = [
            ("tipoGrano", self.sync_tipo_grano),
            ("gradoReferencia", self.sync_grado_referencia),
            ("gradoEntregado", self.sync_grado_entregado),
            ("puerto", self.sync_puertos),
            ("provincia", self.sync_provincias),
            ("tipoDeduccion", self.sync_tipo_deduccion),
            ("tipoRetencion", self.sync_tipo_retencion),
            ("tipoOperacion", self.sync_tipo_operacion),
            # localidades se sincroniza despues de provincias
            ("localidad", self.sync_localidades),
        ]
        for name, method in methods:
            try:
                results[name] = method()
            except Exception as exc:
                logger.exception("PARAM_SYNC_ERROR | tabla=%s", name)
                results[name] = {"tabla": name, "synced": 0, "error": str(exc)}
        return results
```

**Step 4: Run tests to verify pass**

Run: `cd backend && python3 -m pytest tests/unit/test_parameter_sync.py -v`
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add backend/app/services/parameter_sync.py backend/tests/unit/test_parameter_sync.py
git commit -m "feat: add ParameterSyncService for WSLPG parametric tables"
```

---

## Task 3: DatosLimpiosBuilder - Transformar raw_data a datos enriquecidos

**Files:**
- Create: `backend/app/services/datos_limpios_builder.py`
- Test: `backend/tests/unit/test_datos_limpios_builder.py`

**Step 1: Write the failing test**

```python
# backend/tests/unit/test_datos_limpios_builder.py
from __future__ import annotations

from app.extensions import db
from app.models import WslpgParameter, LpgDocument, Taxpayer
from app.services.datos_limpios_builder import DatosLimpiosBuilder


def _seed_parameters():
    """Carga parametros minimos para tests."""
    params = [
        ("tipoGrano", "15", "TRIGO PAN"),
        ("gradoReferencia", "G2", "Grado 2"),
        ("gradoEntregado", "G2", "Grado 2"),
        ("puerto", "14", "OTROS"),
        ("provincia", "3", "CORDOBA"),
        ("localidad", "3_1443", "BENGOLEA"),
        ("tipoDeduccion", "OD", "Otras Deducciones"),
        ("tipoDeduccion", "GA", "Comision o Gastos Administrativos"),
        ("tipoRetencion", "RG", "Retencion Ganancias"),
        ("tipoRetencion", "RI", "Retencion IVA"),
        ("tipoOperacion", "2", "Consignacion"),
    ]
    for tabla, codigo, desc in params:
        db.session.add(WslpgParameter(tabla=tabla, codigo=codigo, descripcion=desc))
    db.session.commit()


SAMPLE_RAW_DATA = {
    "data": {
        "codTipoOperacion": 2,
        "coe": 330230101658,
        "fechaLiquidacion": "2025-12-15",
        "cuitComprador": 30500120882,
        "cuitVendedor": 30711165378,
        "precioRefTn": 278265,
        "codGradoRef": "G2",
        "codGrano": 15,
        "precioFleteTn": 0,
        "codPuerto": 14,
        "nroCertificadoDeposito": 332021671471,
        "codGradoEnt": "G2",
        "factorEnt": 95.3,
        "contProteico": 9.1,
        "pesoNeto": 29086,
        "codLocalidadProcedencia": 1443,
        "codProvProcedencia": 3,
        "totalPesoNeto": 29086,
        "precioOperacion": 265.187,
        "subTotal": 7713215.85,
        "alicIvaOperacion": 10.5,
        "importeIva": 809887.66,
        "operacionConIva": 8523103.51,
        "deducciones": [
            {
                "codigoConcepto": "OD",
                "detalleAclaratorio": "Derecho de Registro Cordoba",
                "baseCalculo": 80936.16,
                "alicuotaIva": 10.5,
                "importeIva": 8498.3,
                "importeDeduccion": 89434.46,
            }
        ],
        "retenciones": [
            {
                "codigoConcepto": "RG",
                "detalleAclaratorio": "Detalle de Ret.Gan.",
                "nroCertificadoRetencion": None,
                "importeCertificadoRetencion": None,
                "fechaCertificadoRetencion": None,
                "baseCalculo": 7632279.6,
                "alicuota": 5,
                "importeRetencion": 381613.98,
            }
        ],
        "totalRetencionAfip": 381613.98,
        "totalNetoAPagar": 8042896.33,
        "totalPercepcion": 0,
        "totalOtrasRetenciones": 0,
        "totalIvaRg4310_18": 419775.38,
        "totalDeduccion": 98593.2,
        "totalPagoSegunCondicion": 7623120.95,
    }
}


def test_build_datos_limpios(app):
    with app.app_context():
        _seed_parameters()
        builder = DatosLimpiosBuilder()
        result = builder.build(SAMPLE_RAW_DATA)

        # General
        assert result["codTipoOperacion"] == 2
        assert result["descTipoOperacion"] == "Consignacion"
        assert result["coe"] == 330230101658
        assert result["fechaLiquidacion"] == "2025-12-15"

        # Comprador / Vendedor
        assert result["cuitComprador"] == 30500120882
        assert result["cuitVendedor"] == 30711165378

        # Condiciones
        assert result["descGrano"] == "TRIGO PAN"
        assert result["descGradoRef"] == "Grado 2"
        assert result["descPuerto"] == "OTROS"

        # Mercaderia
        assert result["descGradoEnt"] == "Grado 2"
        assert result["descLocalidadProcedencia"] == "BENGOLEA"
        assert result["descProvProcedencia"] == "CORDOBA"

        # Deducciones
        assert len(result["deducciones"]) == 1
        assert result["deducciones"][0]["descConcepto"] == "Otras Deducciones"

        # Retenciones
        assert len(result["retenciones"]) == 1
        assert result["retenciones"][0]["descConcepto"] == "Retencion Ganancias"

        # Totales
        assert result["totalPagoSegunCondicion"] == 7623120.95


def test_build_with_missing_params_uses_fallback(app):
    """Si no existen parametros, usa codigo como fallback."""
    with app.app_context():
        # No seed — tabla parametrica vacia
        builder = DatosLimpiosBuilder()
        result = builder.build(SAMPLE_RAW_DATA)

        assert result["descGrano"] == "15"
        assert result["descPuerto"] == "14"


def test_build_with_no_data_key(app):
    """raw_data sin envoltorio 'data' (posible caso legacy)."""
    with app.app_context():
        _seed_parameters()
        raw = dict(SAMPLE_RAW_DATA["data"])  # sin envoltorio
        builder = DatosLimpiosBuilder()
        result = builder.build(raw)

        assert result["descGrano"] == "TRIGO PAN"


def test_build_with_none(app):
    with app.app_context():
        builder = DatosLimpiosBuilder()
        result = builder.build(None)
        assert result == {}


def test_process_document(app):
    """Verifica que process_document guarda datos_limpios en el LpgDocument."""
    with app.app_context():
        _seed_parameters()

        taxpayer = Taxpayer()
        taxpayer.cuit = "20111111111"
        taxpayer.empresa = "Test SA"
        taxpayer.cuit_representado = "20111111111"
        taxpayer.clave_fiscal_encrypted = "x"
        db.session.add(taxpayer)
        db.session.commit()

        doc = LpgDocument()
        doc.taxpayer_id = taxpayer.id
        doc.coe = "330230101658"
        doc.estado = "AC"
        doc.tipo_documento = "LPG"
        doc.raw_data = SAMPLE_RAW_DATA
        db.session.add(doc)
        db.session.commit()

        builder = DatosLimpiosBuilder()
        builder.process_document(doc)

        refreshed = db.session.get(LpgDocument, doc.id)
        assert refreshed.datos_limpios is not None
        assert refreshed.datos_limpios["descGrano"] == "TRIGO PAN"
```

**Step 2: Run test to verify fails**

Run: `cd backend && python3 -m pytest tests/unit/test_datos_limpios_builder.py -v`
Expected: FAIL — ImportError

**Step 3: Add datos_limpios column to LpgDocument**

Add to `backend/app/models/lpg_document.py`:
```python
datos_limpios = db.Column(db.JSON, nullable=True)
```

Add migration:
```python
# en la misma migracion 20260306_0004 o una nueva 20260306_0005
# op.add_column("lpg_document", sa.Column("datos_limpios", sa.JSON(), nullable=True))
```

**Step 4: Write DatosLimpiosBuilder**

```python
# backend/app/services/datos_limpios_builder.py
from __future__ import annotations

import logging
from typing import Any

from ..extensions import db
from ..models import WslpgParameter
from ..models.lpg_document import LpgDocument

logger = logging.getLogger(__name__)


class DatosLimpiosBuilder:
    """Transforma raw_data de un LpgDocument en datos enriquecidos con descripciones."""

    def build(self, raw_data: dict | None) -> dict[str, Any]:
        if not raw_data:
            return {}

        # Desenvolver {"data": {...}} si corresponde
        data = raw_data.get("data", raw_data) if isinstance(raw_data, dict) else {}
        if not isinstance(data, dict):
            return {}

        result: dict[str, Any] = {}

        # --- General ---
        result["codTipoOperacion"] = data.get("codTipoOperacion")
        result["descTipoOperacion"] = self._resolve("tipoOperacion", data.get("codTipoOperacion"))
        result["coe"] = data.get("coe")
        result["fechaLiquidacion"] = data.get("fechaLiquidacion")

        # --- Comprador / Vendedor ---
        result["cuitComprador"] = data.get("cuitComprador")
        result["cuitVendedor"] = data.get("cuitVendedor")

        # --- Condiciones ---
        result["precioRefTn"] = data.get("precioRefTn")
        result["codGradoRef"] = data.get("codGradoRef")
        result["descGradoRef"] = self._resolve("gradoReferencia", data.get("codGradoRef"))
        result["codGrano"] = data.get("codGrano")
        result["descGrano"] = self._resolve("tipoGrano", data.get("codGrano"))
        result["precioFleteTn"] = data.get("precioFleteTn")
        result["codPuerto"] = data.get("codPuerto")
        result["descPuerto"] = self._resolve("puerto", data.get("codPuerto"))

        # --- Mercaderia ---
        result["nroCertificadoDeposito"] = data.get("nroCertificadoDeposito")
        result["codGradoEnt"] = data.get("codGradoEnt")
        result["descGradoEnt"] = self._resolve("gradoEntregado", data.get("codGradoEnt"))
        result["factorEnt"] = data.get("factorEnt")
        result["contProteico"] = data.get("contProteico")
        result["pesoNeto"] = data.get("pesoNeto")

        cod_prov = data.get("codProvProcedencia")
        cod_loc = data.get("codLocalidadProcedencia")
        result["codLocalidadProcedencia"] = cod_loc
        result["codProvProcedencia"] = cod_prov
        result["descProvProcedencia"] = self._resolve("provincia", cod_prov)
        result["descLocalidadProcedencia"] = self._resolve(
            "localidad", f"{cod_prov}_{cod_loc}" if cod_prov and cod_loc else None
        )

        # --- Operacion ---
        result["totalPesoNeto"] = data.get("totalPesoNeto")
        result["precioOperacion"] = data.get("precioOperacion")
        result["subTotal"] = data.get("subTotal")
        result["alicIvaOperacion"] = data.get("alicIvaOperacion")
        result["importeIva"] = data.get("importeIva")
        result["operacionConIva"] = data.get("operacionConIva")

        # --- Deducciones ---
        raw_deds = data.get("deducciones", [])
        if not isinstance(raw_deds, list):
            raw_deds = [raw_deds] if raw_deds else []
        result["deducciones"] = [self._enrich_deduccion(d) for d in raw_deds]

        # --- Retenciones ---
        raw_rets = data.get("retenciones", [])
        if not isinstance(raw_rets, list):
            raw_rets = [raw_rets] if raw_rets else []
        result["retenciones"] = [self._enrich_retencion(r) for r in raw_rets]

        # --- Totales ---
        for key in (
            "operacionConIva", "totalRetencionAfip", "totalNetoAPagar",
            "totalPercepcion", "totalOtrasRetenciones", "totalIvaRg4310_18",
            "totalDeduccion", "totalPagoSegunCondicion",
        ):
            result[key] = data.get(key)

        return result

    def process_document(self, doc: LpgDocument) -> None:
        doc.datos_limpios = self.build(doc.raw_data)
        db.session.commit()

    def process_all(self) -> int:
        docs = LpgDocument.query.filter(LpgDocument.raw_data.isnot(None)).all()
        count = 0
        for doc in docs:
            doc.datos_limpios = self.build(doc.raw_data)
            count += 1
        db.session.commit()
        logger.info("DATOS_LIMPIOS_REBUILD | total=%d", count)
        return count

    def _resolve(self, tabla: str, codigo: Any) -> str:
        if codigo is None:
            return ""
        desc = WslpgParameter.lookup(tabla, str(codigo))
        return desc if desc else str(codigo)

    def _enrich_deduccion(self, raw: dict) -> dict:
        return {
            **raw,
            "descConcepto": self._resolve("tipoDeduccion", raw.get("codigoConcepto")),
        }

    def _enrich_retencion(self, raw: dict) -> dict:
        return {
            **raw,
            "descConcepto": self._resolve("tipoRetencion", raw.get("codigoConcepto")),
        }
```

**Step 5: Run tests to verify pass**

Run: `cd backend && python3 -m pytest tests/unit/test_datos_limpios_builder.py -v`
Expected: 5 PASSED

**Step 6: Commit**

```bash
git add backend/app/services/datos_limpios_builder.py \
  backend/app/models/lpg_document.py \
  backend/tests/unit/test_datos_limpios_builder.py
git commit -m "feat: add DatosLimpiosBuilder to enrich COE raw_data with descriptions"
```

---

## Task 4: API endpoints para sync y rebuild

**Files:**
- Modify: `backend/app/api/discovery.py` (agregar endpoints de sync)
- Test: `backend/tests/integration/test_parameter_sync_api.py`

**Step 1: Write failing test**

```python
# backend/tests/integration/test_parameter_sync_api.py
from __future__ import annotations

from app.extensions import db
from app.models import WslpgParameter, Taxpayer, LpgDocument


def _create_doc_with_raw_data(taxpayer_id: int) -> LpgDocument:
    doc = LpgDocument()
    doc.taxpayer_id = taxpayer_id
    doc.coe = "330230101658"
    doc.estado = "AC"
    doc.tipo_documento = "LPG"
    doc.raw_data = {"data": {"codGrano": 15, "codPuerto": 14}}
    db.session.add(doc)
    db.session.commit()
    return doc


def test_rebuild_datos_limpios(client):
    """POST /api/admin/rebuild-datos-limpios reprocesa todos los documentos."""
    # Crear taxpayer y documento
    taxpayer = Taxpayer()
    taxpayer.cuit = "20111111111"
    taxpayer.empresa = "Test SA"
    taxpayer.cuit_representado = "20111111111"
    taxpayer.clave_fiscal_encrypted = "x"
    db.session.add(taxpayer)
    db.session.commit()

    doc = _create_doc_with_raw_data(taxpayer.id)

    # Cargar algun parametro para que se enriquezca
    db.session.add(WslpgParameter(tabla="tipoGrano", codigo="15", descripcion="TRIGO PAN"))
    db.session.add(WslpgParameter(tabla="puerto", codigo="14", descripcion="OTROS"))
    db.session.commit()

    response = client.post("/api/admin/rebuild-datos-limpios")
    assert response.status_code == 200
    data = response.get_json()
    assert data["processed"] == 1

    # Verificar que datos_limpios fue generado
    refreshed = db.session.get(LpgDocument, doc.id)
    assert refreshed.datos_limpios is not None
    assert refreshed.datos_limpios["descGrano"] == "TRIGO PAN"
```

**Step 2: Run test to verify fails**

Run: `cd backend && python3 -m pytest tests/integration/test_parameter_sync_api.py -v`
Expected: FAIL — 404

**Step 3: Write endpoints**

Agregar a `backend/app/api/discovery.py` (o crear `admin.py` dedicado):

```python
# Agregar al final de discovery.py o crear backend/app/api/admin.py

from ..services.datos_limpios_builder import DatosLimpiosBuilder

@discovery_bp.post("/admin/rebuild-datos-limpios")
def rebuild_datos_limpios():
    try:
        builder = DatosLimpiosBuilder()
        count = builder.process_all()
        return jsonify({"processed": count})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@discovery_bp.post("/admin/sync-parameters")
def sync_parameters():
    """Sincroniza tablas parametricas desde WSLPG. Requiere credenciales ARCA configuradas."""
    try:
        from ..services.parameter_sync import ParameterSyncService
        client = ArcaWslpgClient()
        client.connect()
        service = ParameterSyncService(client)
        results = service.sync_all()
        return jsonify(results)
    except ArcaIntegrationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error en sync: {exc}"}), 500
```

**Step 4: Run test to verify pass**

Run: `cd backend && python3 -m pytest tests/integration/test_parameter_sync_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/api/discovery.py backend/tests/integration/test_parameter_sync_api.py
git commit -m "feat: add admin endpoints for parameter sync and datos_limpios rebuild"
```

---

## Task 5: Migracion para columna datos_limpios

**Files:**
- Create: `backend/migrations/versions/20260306_0005_add_datos_limpios.py`

**Step 1: Write migration**

```python
# backend/migrations/versions/20260306_0005_add_datos_limpios.py
"""Add datos_limpios column to lpg_document

Revision ID: 20260306_0005
Revises: 20260306_0004
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = "20260306_0005"
down_revision = "20260306_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lpg_document", sa.Column("datos_limpios", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("lpg_document", "datos_limpios")
```

**Step 2: Run all tests to verify nothing breaks**

Run: `cd backend && python3 -m pytest -q`
Expected: All PASSED

**Step 3: Commit**

```bash
git add backend/migrations/versions/20260306_0005_add_datos_limpios.py
git commit -m "feat: migration add datos_limpios column to lpg_document"
```

---

## Task 6: Frontend - Consumir datos_limpios en CoeDetailPage

**Files:**
- Modify: `frontend/src/api/coes.ts` (agregar datos_limpios al tipo)
- Modify: `frontend/src/pages/CoeDetailPage.tsx` (usar datos_limpios en vez de raw_data para DatosLimpiosSection)

**Step 1: Actualizar tipo Coe**

En `frontend/src/api/coes.ts`, agregar al interface `Coe`:
```typescript
datos_limpios: Record<string, unknown> | null;
```

**Step 2: Actualizar CoeDetailPage para usar datos_limpios**

En `DatosLimpiosSection`, cambiar para:
- Usar `datos_limpios` si existe, con fallback a `raw_data.data` o `raw_data`
- Mostrar `descGrano` en vez de mapeo local GRANOS
- Mostrar `descGradoRef`, `descPuerto`, `descLocalidadProcedencia`, etc.
- Mostrar `descConcepto` en deducciones y retenciones

Eliminar los mapeos hardcodeados `GRANOS` y `TIPOS_OPERACION`.

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: BUILD OK

**Step 4: Commit**

```bash
git add frontend/src/api/coes.ts frontend/src/pages/CoeDetailPage.tsx
git commit -m "feat(frontend): use datos_limpios for enriched COE display"
```

---

## Task 7: Backend exportacion - Usar datos_limpios

**Files:**
- Modify: `backend/app/api/clients.py` (actualizar _build_export_row para usar datos_limpios)

**Step 1: Actualizar _build_export_row**

Cambiar `_build_export_row` para priorizar `doc.datos_limpios` sobre `doc.raw_data`:
- Si `datos_limpios` existe, leer de ahi (ya tiene campos planos + descripciones)
- Agregar columnas de descripcion al export: `descGrano`, `descGradoRef`, `descPuerto`, etc.
- Actualizar EXPORT_FIELDNAMES

**Step 2: Verify**

Run: `cd backend && python3 -m compileall app -q`
Expected: OK

**Step 3: Commit**

```bash
git add backend/app/api/clients.py
git commit -m "feat: export uses datos_limpios with enriched descriptions"
```

---

## Task 8: Integrar DatosLimpiosBuilder en el pipeline de extraccion

**Files:**
- Modify: `backend/app/services/lpg_playwright_pipeline.py` (llamar builder despues de guardar documento)

**Step 1: En _save_lpg_document, despues del commit, generar datos_limpios**

```python
# Despues de db.session.commit() en _save_lpg_document:
from .datos_limpios_builder import DatosLimpiosBuilder
builder = DatosLimpiosBuilder()
builder.process_document(document)
```

**Step 2: Verify all tests pass**

Run: `cd backend && python3 -m pytest -q`
Expected: All PASSED

**Step 3: Commit**

```bash
git add backend/app/services/lpg_playwright_pipeline.py
git commit -m "feat: auto-generate datos_limpios on COE extraction"
```

---

## Resumen del flujo completo

```
1. Admin ejecuta POST /api/admin/sync-parameters
   → ParameterSyncService llama metodos SOAP de maestros
   → Guarda en tabla wslpg_parameter (tipoGrano, puerto, etc.)

2. Admin ejecuta POST /api/admin/rebuild-datos-limpios  (unica vez)
   → DatosLimpiosBuilder lee raw_data de cada LpgDocument
   → Resuelve codigos contra wslpg_parameter
   → Guarda resultado en datos_limpios

3. Nuevos COEs extraidos por pipeline
   → _save_lpg_document ya llama DatosLimpiosBuilder automaticamente

4. Frontend /coes/:id muestra datos_limpios con descripciones

5. Exportacion CSV/XLSX incluye descripciones de datos_limpios
```
