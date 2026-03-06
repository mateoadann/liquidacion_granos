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
