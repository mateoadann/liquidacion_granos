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

        # Detectar si es un ajuste (estructura ajusteUnificado)
        ajuste_unif = data.get("ajusteUnificado")
        if isinstance(ajuste_unif, dict) and ajuste_unif:
            return self._build_ajuste(ajuste_unif)

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

    def _build_ajuste(self, ajuste: dict) -> dict[str, Any]:
        """Construye datos limpios para un COE de tipo ajuste."""
        result: dict[str, Any] = {"es_ajuste": True}

        result["codTipoOperacion"] = ajuste.get("codTipoOperacion")
        result["descTipoOperacion"] = self._resolve("tipoOperacion", result["codTipoOperacion"])
        result["coe"] = ajuste.get("coe")
        result["coeAjustado"] = ajuste.get("coeAjustado")
        result["estado"] = ajuste.get("estado")
        result["ptoEmision"] = ajuste.get("ptoEmision")
        result["nroOrden"] = ajuste.get("nroOrden")
        result["nroContrato"] = ajuste.get("nroContrato")

        for lado in ("ajusteCredito", "ajusteDebito"):
            sec = ajuste.get(lado, {}) or {}
            if not isinstance(sec, dict):
                continue
            prefix = "credito" if "Credito" in lado else "debito"
            result[f"{prefix}_fechaLiquidacion"] = sec.get("fechaLiquidacion")
            result[f"{prefix}_precioOperacion"] = sec.get("precioOperacion")
            result[f"{prefix}_subTotal"] = sec.get("subTotal")
            result[f"{prefix}_importeIva"] = sec.get("importeIva")
            result[f"{prefix}_operacionConIva"] = sec.get("operacionConIva")
            result[f"{prefix}_totalPesoNeto"] = sec.get("totalPesoNeto")
            result[f"{prefix}_totalDeduccion"] = sec.get("totalDeduccion")
            result[f"{prefix}_totalRetencion"] = sec.get("totalRetencion")
            result[f"{prefix}_totalRetencionAfip"] = sec.get("totalRetencionAfip")
            result[f"{prefix}_totalOtrasRetenciones"] = sec.get("totalOtrasRetenciones")
            result[f"{prefix}_totalNetoAPagar"] = sec.get("totalNetoAPagar")
            result[f"{prefix}_totalPagoSegunCondicion"] = sec.get("totalPagoSegunCondicion")

            # Deducciones y retenciones por lado
            raw_deds_wrap = sec.get("deducciones", {})
            if isinstance(raw_deds_wrap, dict):
                raw_deds = raw_deds_wrap.get("deduccionReturn", [])
            elif isinstance(raw_deds_wrap, list):
                raw_deds = raw_deds_wrap
            else:
                raw_deds = []
            if not isinstance(raw_deds, list):
                raw_deds = [raw_deds] if raw_deds else []
            result[f"{prefix}_deducciones"] = [self._enrich_deduccion(d) for d in raw_deds]

            raw_rets_wrap = sec.get("retenciones", {})
            if isinstance(raw_rets_wrap, dict):
                raw_rets = raw_rets_wrap.get("retencionReturn", [])
            elif isinstance(raw_rets_wrap, list):
                raw_rets = raw_rets_wrap
            else:
                raw_rets = []
            if not isinstance(raw_rets, list):
                raw_rets = [raw_rets] if raw_rets else []
            result[f"{prefix}_retenciones"] = [self._enrich_retencion(r) for r in raw_rets]

        # Totales unificados
        totales = ajuste.get("totalesUnificados", {}) or {}
        if isinstance(totales, dict):
            for key in (
                "subTotalDebCred", "totalBaseDeducciones", "subTotalGeneral",
                "ivaDeducciones", "iva105", "iva21", "retencionesGanancias",
                "retencionesIVA", "importeOtrasRetenciones", "importeNeto",
                "ivaRG4310_18", "pagoSCondicion",
            ):
                result[f"totales_{key}"] = totales.get(key)

        return result

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
