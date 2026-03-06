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
        from ..integrations.arca.client import _safe_serialize

        data = {"auth": self._ws.get_auth_payload()}
        if extra_data:
            data.update(extra_data)
        result = self._ws.send_request(method, data)
        serialized = _safe_serialize(result)
        return serialized.get("data", serialized)

    def _extract_rows(self, data: dict, wrapper_key: str) -> list[dict]:
        """Extrae filas de la estructura SOAP: data[wrapper_key].codigoDescripcion -> [{codigo, descripcion}]"""
        wrapper = data.get(wrapper_key, {}) if isinstance(data, dict) else {}
        if isinstance(wrapper, dict):
            rows = wrapper.get("codigoDescripcion", [])
        elif isinstance(wrapper, list):
            rows = wrapper
        else:
            rows = []
        if not isinstance(rows, list):
            rows = [rows] if rows else []
        return rows

    def sync_tipo_grano(self) -> dict:
        data = self._call("tipoGranoConsultar")
        rows = self._extract_rows(data, "granos")
        return self._upsert_rows("tipoGrano", rows, "codigo", "descripcion")

    def sync_grado_referencia(self) -> dict:
        data = self._call("codigoGradoReferenciaConsultar")
        rows = self._extract_rows(data, "gradosRef")
        return self._upsert_rows("gradoReferencia", rows, "codigo", "descripcion")

    def sync_grado_entregado(self) -> dict:
        # Grados entregados son iguales para todos los granos (solo cambia el valor/factor).
        # Consultamos con un solo grano (15=TRIGO PAN) para obtener los códigos+descripciones.
        # Estructura: data.gradoEnt.gradoEnt[] -> {codigoDescripcion: {codigo, desc}, valor}
        data = self._call("codigoGradoEntregadoXTipoGranoConsultar", {"codGrano": 15})
        wrapper = data.get("gradoEnt", {}) if isinstance(data, dict) else {}
        items = wrapper.get("gradoEnt", []) if isinstance(wrapper, dict) else []
        if not isinstance(items, list):
            items = [items] if items else []
        rows = []
        for item in items:
            cd = item.get("codigoDescripcion", {}) if isinstance(item, dict) else {}
            code = cd.get("codigo", "")
            if code:
                rows.append({"codigo": code, "descripcion": cd.get("descripcion", "")})
        return self._upsert_rows("gradoEntregado", rows, "codigo", "descripcion")

    def sync_puertos(self) -> dict:
        data = self._call("puertoConsultar")
        rows = self._extract_rows(data, "puertos")
        return self._upsert_rows("puerto", rows, "codigo", "descripcion")

    def sync_provincias(self) -> dict:
        data = self._call("provinciasConsultar")
        rows = self._extract_rows(data, "provincias")
        return self._upsert_rows("provincia", rows, "codigo", "descripcion")

    def sync_localidades(self, cod_provincia: int | None = None) -> dict:
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
        rows = self._extract_rows(data, "localidades")
        enriched = []
        for row in rows:
            row_copy = dict(row)
            row_copy["_cod_compuesto"] = f"{cod_provincia}_{row.get('codigo', '')}"
            row_copy["_desc_localidad"] = str(row.get("descripcion", ""))
            enriched.append(row_copy)
        return self._upsert_rows("localidad", enriched, "_cod_compuesto", "_desc_localidad")

    def sync_tipo_deduccion(self) -> dict:
        data = self._call("tipoDeduccionConsultar")
        rows = self._extract_rows(data, "tiposDeduccion")
        return self._upsert_rows("tipoDeduccion", rows, "codigo", "descripcion")

    def sync_tipo_retencion(self) -> dict:
        data = self._call("tipoRetencionConsultar")
        rows = self._extract_rows(data, "tiposRetencion")
        return self._upsert_rows("tipoRetencion", rows, "codigo", "descripcion")

    def sync_tipo_operacion(self) -> dict:
        # Los tipos de operación son valores estándar fijos del WSLPG
        rows = [
            {"codigo": "1", "descripcion": "Compra-venta de granos"},
            {"codigo": "2", "descripcion": "Consignación de granos"},
            {"codigo": "3", "descripcion": "Propia (acopiador/consignatario)"},
            {"codigo": "4", "descripcion": "Propia (industrial)"},
        ]
        return self._upsert_rows("tipoOperacion", rows, "codigo", "descripcion")

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
            ("localidad", self.sync_localidades),
        ]
        for name, method in methods:
            try:
                results[name] = method()
            except Exception as exc:
                logger.exception("PARAM_SYNC_ERROR | tabla=%s", name)
                results[name] = {"tabla": name, "synced": 0, "error": str(exc)}
        return results
