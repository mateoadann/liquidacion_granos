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

        # La estructura real es: data.autorizacion (totales, ded, ret) + data.liquidacion (grano, comprador, etc.)
        aut = data.get("autorizacion", {}) or {}
        liq = data.get("liquidacion", {}) or {}
        # Si no hay subniveles, intentar leer flat (compatibilidad)
        if not aut and not liq:
            aut = data
            liq = data

        result: dict[str, Any] = {}

        # --- General ---
        result["codTipoOperacion"] = aut.get("codTipoOperacion") or liq.get("codTipoOperacion")
        result["descTipoOperacion"] = self._resolve("tipoOperacion", result["codTipoOperacion"])
        result["coe"] = aut.get("coe")
        result["fechaLiquidacion"] = aut.get("fechaLiquidacion")

        # --- Comprador / Vendedor ---
        result["cuitComprador"] = liq.get("cuitComprador")
        result["cuitVendedor"] = liq.get("cuitVendedor")

        # --- Condiciones ---
        result["precioRefTn"] = liq.get("precioRefTn")
        result["codGradoRef"] = liq.get("codGradoRef")
        result["descGradoRef"] = self._resolve("gradoReferencia", liq.get("codGradoRef"))
        result["codGrano"] = liq.get("codGrano")
        result["descGrano"] = self._resolve("tipoGrano", liq.get("codGrano"))
        result["precioFleteTn"] = liq.get("precioFleteTn")
        result["codPuerto"] = liq.get("codPuerto")
        result["descPuerto"] = self._resolve("puerto", liq.get("codPuerto"))

        # --- Mercaderia (del primer certificado si existe) ---
        certs = liq.get("certificados", {})
        cert_list = certs.get("certificado", []) if isinstance(certs, dict) else []
        if isinstance(cert_list, dict):
            cert_list = [cert_list]
        first_cert = cert_list[0] if cert_list else {}

        result["nroCertificadoDeposito"] = first_cert.get("nroCertificadoDeposito")
        result["codGradoEnt"] = liq.get("codGradoEnt")
        result["descGradoEnt"] = self._resolve("gradoEntregado", liq.get("codGradoEnt"))
        result["factorEnt"] = liq.get("factorEnt") or liq.get("valGradoEnt")
        result["contProteico"] = liq.get("contProteico")
        result["pesoNeto"] = first_cert.get("pesoNeto")

        cod_prov = liq.get("codProvProcedencia")
        cod_loc = liq.get("codLocalidadProcedencia")
        result["codLocalidadProcedencia"] = cod_loc
        result["codProvProcedencia"] = cod_prov
        result["descProvProcedencia"] = self._resolve("provincia", cod_prov)
        result["descLocalidadProcedencia"] = self._resolve(
            "localidad", f"{cod_prov}_{cod_loc}" if cod_prov and cod_loc else None
        )

        # --- Operacion ---
        result["totalPesoNeto"] = aut.get("totalPesoNeto")
        result["precioOperacion"] = aut.get("precioOperacion")
        result["subTotal"] = aut.get("subTotal")
        result["alicIvaOperacion"] = liq.get("alicIvaOperacion")
        result["importeIva"] = aut.get("importeIva")
        result["operacionConIva"] = aut.get("operacionConIva")

        # --- Deducciones ---
        raw_deds_wrap = aut.get("deducciones", {})
        if isinstance(raw_deds_wrap, dict):
            raw_deds = raw_deds_wrap.get("deduccionReturn", [])
        elif isinstance(raw_deds_wrap, list):
            raw_deds = raw_deds_wrap
        else:
            raw_deds = []
        if not isinstance(raw_deds, list):
            raw_deds = [raw_deds] if raw_deds else []
        result["deducciones"] = [self._enrich_deduccion(d) for d in raw_deds]

        # --- Retenciones ---
        raw_rets_wrap = aut.get("retenciones", {})
        if isinstance(raw_rets_wrap, dict):
            raw_rets = raw_rets_wrap.get("retencionReturn", [])
        elif isinstance(raw_rets_wrap, list):
            raw_rets = raw_rets_wrap
        else:
            raw_rets = []
        if not isinstance(raw_rets, list):
            raw_rets = [raw_rets] if raw_rets else []
        result["retenciones"] = [self._enrich_retencion(r) for r in raw_rets]

        # --- Totales ---
        for key in (
            "operacionConIva", "totalRetencionAfip", "totalNetoAPagar",
            "totalPercepcion", "totalOtrasRetenciones", "totalIvaRg4310_18",
            "totalDeduccion", "totalPagoSegunCondicion",
        ):
            result[key] = aut.get(key)

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
        # Estructura: {deduccion: {codigoConcepto, detalleAclaratorio, ...}, importeDeduccion, importeIva}
        inner = raw.get("deduccion", {}) if isinstance(raw, dict) else {}
        if not isinstance(inner, dict):
            inner = {}
        result = {**raw}
        result["codigoConcepto"] = inner.get("codigoConcepto")
        result["detalleAclaratorio"] = inner.get("detalleAclaratorio")
        result["baseCalculo"] = inner.get("baseCalculo")
        result["alicuotaIva"] = inner.get("alicuotaIva")
        result["descConcepto"] = self._resolve("tipoDeduccion", inner.get("codigoConcepto"))
        return result

    def _enrich_retencion(self, raw: dict) -> dict:
        # Estructura: {retencion: {codigoConcepto, detalleAclaratorio, ...}, importeRetencion}
        inner = raw.get("retencion", {}) if isinstance(raw, dict) else {}
        if not isinstance(inner, dict):
            inner = {}
        result = {**raw}
        result["codigoConcepto"] = inner.get("codigoConcepto")
        result["detalleAclaratorio"] = inner.get("detalleAclaratorio")
        result["baseCalculo"] = inner.get("baseCalculo")
        result["alicuota"] = inner.get("alicuota")
        result["nroCertificadoRetencion"] = inner.get("nroCertificadoRetencion")
        result["importeCertificadoRetencion"] = inner.get("importeCertificadoRetencion")
        result["fechaCertificadoRetencion"] = inner.get("fechaCertificadoRetencion")
        result["descConcepto"] = self._resolve("tipoRetencion", inner.get("codigoConcepto"))
        return result
