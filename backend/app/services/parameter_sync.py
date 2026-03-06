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
        data = {"auth": self._ws.get_auth_payload()}
        if extra_data:
            data.update(extra_data)
        result = self._ws.send_request(method, data)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result

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
