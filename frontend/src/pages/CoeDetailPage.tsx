import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, CardHeader, Badge, Button, Spinner, Alert } from "../components/ui";
import { useCoeQuery } from "../hooks/useCoes";
import { usePersonaQuery } from "../hooks/usePadron";
import { downloadCoePdf } from "../api/coes";
import { formatDateOnly, formatDateTime } from "../dateUtils";

function EstadoBadge({ estado }: { estado: string | null }) {
  const variants: Record<string, "success" | "warning" | "error" | "default"> = {
    AC: "success",
    AN: "error",
    PE: "warning",
  };
  const labels: Record<string, string> = {
    AC: "Activo",
    AN: "Anulado",
    PE: "Pendiente",
  };
  return (
    <Badge variant={variants[estado ?? ""] ?? "default"}>
      {labels[estado ?? ""] ?? estado ?? "-"}
    </Badge>
  );
}

function CoeEstadoBadge({ estado }: { estado: string | null }) {
  const variants: Record<string, "success" | "warning" | "error" | "default"> = {
    pendiente: "warning",
    descargado: "default",
    cargado: "success",
    error: "error",
  };
  const labels: Record<string, string> = {
    pendiente: "Pendiente",
    descargado: "Descargado",
    cargado: "Cargado",
    error: "Error",
  };
  if (!estado) return <span className="text-sm text-slate-400">Sin tracking</span>;
  return (
    <Badge variant={variants[estado] ?? "default"}>
      {labels[estado] ?? estado}
    </Badge>
  );
}

// Helper para formatear números como moneda
function formatCurrency(value: unknown): string {
  if (value === null || value === undefined) return "-";
  const num = typeof value === "number" ? value : parseFloat(String(value));
  if (isNaN(num)) return "-";
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
  }).format(num);
}

// Helper para formatear números
function formatNumber(value: unknown, decimals = 2): string {
  if (value === null || value === undefined) return "-";
  const num = typeof value === "number" ? value : parseFloat(String(value));
  if (isNaN(num)) return "-";
  return new Intl.NumberFormat("es-AR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num);
}

// Helper para formatear fechas (solo fecha, sin hora) — usa timezone Córdoba
function formatDate(value: unknown): string {
  if (!value) return "-";
  return formatDateOnly(String(value));
}

// Helper: muestra descripción si existe, sino código, sino fallback
function descOrCode(data: Record<string, unknown>, descKey: string, codKey: string, fallback = "-"): string {
  const desc = data[descKey];
  const cod = data[codKey];
  if (desc && typeof desc === "string") return desc;
  if (cod !== null && cod !== undefined) return String(cod);
  return fallback;
}

interface Deduccion {
  codigoConcepto?: string;
  descConcepto?: string;
  detalleAclaratorio?: string;
  baseCalculo?: number;
  alicuotaIva?: number;
  importeIva?: number;
  importeDeduccion?: number;
}

interface Retencion {
  codigoConcepto?: string;
  descConcepto?: string;
  detalleAclaratorio?: string;
  nroCertificadoRetencion?: string | null;
  importeCertificadoRetencion?: number | null;
  fechaCertificadoRetencion?: string | null;
  baseCalculo?: number;
  alicuota?: number;
  importeRetencion?: number;
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="bg-slate-800 text-white px-3 py-2 text-sm font-semibold">
      {title}
    </div>
  );
}

function DataRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between py-1.5 px-3 border-b border-slate-200 last:border-b-0">
      <span className="text-slate-600 text-sm">{label}</span>
      <span className={`text-slate-900 text-sm ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

function PersonaCard({ title, cuit, taxpayerId }: { title: string; cuit: string | null; taxpayerId: number | null }) {
  const cuitStr = cuit ? String(cuit) : null;
  const query = usePersonaQuery(cuitStr, taxpayerId);

  return (
    <div className="border border-slate-300 rounded">
      <SectionHeader title={title} />
      <div className="p-3 space-y-1">
        <DataRow label="C.U.I.T." value={cuitStr ?? "-"} mono />
        {query.isLoading && (
          <p className="text-xs text-slate-400 py-1">Consultando padrón...</p>
        )}
        {query.isError && (
          <p className="text-xs text-red-400 py-1">No se pudo consultar padrón</p>
        )}
        {query.data && (
          <>
            <DataRow label="Razón Social" value={query.data.razonSocial || "-"} />
            <DataRow label="Domicilio" value={query.data.domicilio || "-"} />
            <DataRow label="Localidad" value={[query.data.localidad, query.data.provincia].filter(Boolean).join(", ") || "-"} />
            <DataRow label="I.V.A." value={query.data.condicionIva || "-"} />
          </>
        )}
      </div>
    </div>
  );
}

interface DatosLimpiosProps {
  rawData: Record<string, unknown>;
  datosLimpios: Record<string, unknown> | null;
  taxpayerId: number | null;
}

function DatosLimpiosSection({ rawData, datosLimpios, taxpayerId }: DatosLimpiosProps) {
  // Use datos_limpios if available, otherwise unwrap raw_data.data or use raw_data directly
  const data: Record<string, unknown> = datosLimpios
    ?? (rawData.data && typeof rawData.data === "object" && !Array.isArray(rawData.data)
        ? rawData.data as Record<string, unknown>
        : rawData);

  // Extraer deducciones y retenciones (pueden ser arrays)
  const deducciones = (data["deducciones"] as Deduccion[]) ?? [];
  const retenciones = (data["retenciones"] as Retencion[]) ?? [];

  return (
    <div className="space-y-4">
      {/* Encabezado tipo PDF */}
      <div className="bg-slate-100 border border-slate-300 p-4 rounded-lg">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">LIQUIDACION PRIMARIA DE GRANOS</h3>
            <p className="text-sm text-slate-600 mt-1">
              Tipo de operación: {descOrCode(data, "descTipoOperacion", "codTipoOperacion", "Desconocido")}
            </p>
            <p className="text-sm font-mono text-slate-700">
              C.O.E.: {String(data["coe"] ?? "-")}
            </p>
          </div>
          <div className="text-right text-sm text-slate-600">
            <p>Fecha: {formatDate(data["fechaLiquidacion"])}</p>
          </div>
        </div>

        {/* Comprador y Vendedor */}
        <div className="grid grid-cols-2 gap-4 mt-4">
          <PersonaCard title="COMPRADOR" cuit={data["cuitComprador"] as string | null} taxpayerId={taxpayerId} />
          <PersonaCard title="VENDEDOR" cuit={data["cuitVendedor"] as string | null} taxpayerId={taxpayerId} />
        </div>
      </div>

      {/* Condiciones de la Operación */}
      <div className="border border-slate-300 rounded">
        <SectionHeader title="CONDICIONES DE LA OPERACION" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Precio/TN</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Grado</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Grano</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Flete por TN</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Puerto</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-200">
                <td className="px-3 py-2 font-mono">{formatCurrency(data["precioRefTn"])}</td>
                <td className="px-3 py-2">{descOrCode(data, "descGradoRef", "codGradoRef")}</td>
                <td className="px-3 py-2">{descOrCode(data, "descGrano", "codGrano")}</td>
                <td className="px-3 py-2 font-mono">{formatCurrency(data["precioFleteTn"])}</td>
                <td className="px-3 py-2">{descOrCode(data, "descPuerto", "codPuerto")}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Mercadería Entregada */}
      <div className="border border-slate-300 rounded">
        <SectionHeader title="MERCADERIA ENTREGADA" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Nro Comprobante</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Grado</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Factor</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Cont. Proteico</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Peso Neto</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Procedencia</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-200">
                <td className="px-3 py-2 font-mono">{String(data["nroCertificadoDeposito"] ?? "-")}</td>
                <td className="px-3 py-2">{descOrCode(data, "descGradoEnt", "codGradoEnt")}</td>
                <td className="px-3 py-2">{formatNumber(data["factorEnt"], 1)}</td>
                <td className="px-3 py-2">{formatNumber(data["contProteico"], 1)}</td>
                <td className="px-3 py-2 font-mono">{formatNumber(data["pesoNeto"], 0)} kg</td>
                <td className="px-3 py-2">
                  Loc: {descOrCode(data, "descLocalidadProcedencia", "codLocalidadProcedencia")} /
                  Prov: {descOrCode(data, "descProvProcedencia", "codProvProcedencia")}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Operación */}
      <div className="border border-slate-300 rounded">
        <SectionHeader title="OPERACION" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Cantidad</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Precio/Kg</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Subtotal</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">% Alícuota IVA</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Importe IVA</th>
                <th className="px-3 py-2 text-left text-slate-600 font-medium">Operación c/IVA</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-200">
                <td className="px-3 py-2 font-mono">{formatNumber(data["totalPesoNeto"], 0)} kg</td>
                <td className="px-3 py-2 font-mono">{formatCurrency(data["precioOperacion"])}</td>
                <td className="px-3 py-2 font-mono">{formatCurrency(data["subTotal"])}</td>
                <td className="px-3 py-2">{formatNumber(data["alicIvaOperacion"], 1)}%</td>
                <td className="px-3 py-2 font-mono">{formatCurrency(data["importeIva"])}</td>
                <td className="px-3 py-2 font-mono font-semibold">{formatCurrency(data["operacionConIva"])}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Deducciones */}
      {deducciones.length > 0 && (
        <div className="border border-slate-300 rounded">
          <SectionHeader title="DEDUCCIONES" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Concepto</th>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Detalle</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Base Cálculo</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Alícuota</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Importe IVA</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Deducciones</th>
                </tr>
              </thead>
              <tbody>
                {deducciones.map((ded, idx) => (
                  <tr key={idx} className="border-t border-slate-200">
                    <td className="px-3 py-2">{ded.descConcepto ?? ded.codigoConcepto ?? "-"}</td>
                    <td className="px-3 py-2">{ded.detalleAclaratorio ?? "-"}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(ded.baseCalculo)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(ded.alicuotaIva, 1)}%</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(ded.importeIva)}</td>
                    <td className="px-3 py-2 text-right font-mono font-semibold">{formatCurrency(ded.importeDeduccion)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Retenciones */}
      {retenciones.length > 0 && (
        <div className="border border-slate-300 rounded">
          <SectionHeader title="RETENCIONES" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Concepto</th>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Detalle</th>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Cert. Ret.</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Imp. Cert.</th>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Fecha Cert.</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Base Cálculo</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Alícuota</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Retenciones</th>
                </tr>
              </thead>
              <tbody>
                {retenciones.map((ret, idx) => (
                  <tr key={idx} className="border-t border-slate-200">
                    <td className="px-3 py-2">{ret.descConcepto ?? ret.codigoConcepto ?? "-"}</td>
                    <td className="px-3 py-2">{ret.detalleAclaratorio ?? "-"}</td>
                    <td className="px-3 py-2 font-mono">{ret.nroCertificadoRetencion ?? "-"}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(ret.importeCertificadoRetencion)}</td>
                    <td className="px-3 py-2">{formatDate(ret.fechaCertificadoRetencion)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(ret.baseCalculo)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(ret.alicuota, 0)}%</td>
                    <td className="px-3 py-2 text-right font-mono font-semibold">{formatCurrency(ret.importeRetencion)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Importes Totales */}
      <div className="border border-slate-300 rounded">
        <SectionHeader title="IMPORTES TOTALES DE LA LIQUIDACION" />
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 p-4">
          <div className="space-y-2">
            <DataRow label="Total Operación" value={formatCurrency(data["operacionConIva"])} mono />
            <DataRow label="Total Retenciones AFIP" value={formatCurrency(data["totalRetencionAfip"])} mono />
            <DataRow label="Importe Neto a Pagar" value={formatCurrency(data["totalNetoAPagar"])} mono />
          </div>
          <div className="space-y-2">
            <DataRow label="Total Percepciones" value={formatCurrency(data["totalPercepcion"])} mono />
            <DataRow label="Total Otras Retenciones" value={formatCurrency(data["totalOtrasRetenciones"])} mono />
            <DataRow label="IVA RG 4310/18" value={formatCurrency(data["totalIvaRg4310_18"])} mono />
          </div>
          <div className="space-y-2">
            <DataRow label="Total Deducciones" value={formatCurrency(data["totalDeduccion"])} mono />
            <div className="bg-green-50 border border-green-200 rounded p-2 mt-2">
              <DataRow
                label="Pago según condiciones"
                value={formatCurrency(data["totalPagoSegunCondicion"])}
                mono
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AjusteLadoSection({ data, title }: { data: Record<string, unknown>; title: string }) {
  const deducciones = (data["deducciones"] as Deduccion[]) ?? [];
  const retenciones = (data["retenciones"] as Retencion[]) ?? [];

  return (
    <div className="space-y-3">
      <h4 className="text-md font-bold text-slate-800">{title}</h4>
      <div className="border border-slate-300 rounded">
        <SectionHeader title="OPERACION" />
        <div className="p-3 space-y-1">
          <DataRow label="Fecha Liquidación" value={formatDate(data["fechaLiquidacion"])} />
          <DataRow label="Precio Operación" value={formatCurrency(data["precioOperacion"])} mono />
          <DataRow label="Subtotal" value={formatCurrency(data["subTotal"])} mono />
          <DataRow label="Importe IVA" value={formatCurrency(data["importeIva"])} mono />
          <DataRow label="Operación c/IVA" value={formatCurrency(data["operacionConIva"])} mono />
          <DataRow label="Total Peso Neto" value={formatNumber(data["totalPesoNeto"], 0)} mono />
        </div>
      </div>
      {deducciones.length > 0 && (
        <div className="border border-slate-300 rounded">
          <SectionHeader title="DEDUCCIONES" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Concepto</th>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Detalle</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Importe</th>
                </tr>
              </thead>
              <tbody>
                {deducciones.map((ded, idx) => (
                  <tr key={idx} className="border-t border-slate-200">
                    <td className="px-3 py-2">{ded.descConcepto ?? ded.codigoConcepto ?? "-"}</td>
                    <td className="px-3 py-2">{ded.detalleAclaratorio ?? "-"}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(ded.importeDeduccion)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {retenciones.length > 0 && (
        <div className="border border-slate-300 rounded">
          <SectionHeader title="RETENCIONES" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Concepto</th>
                  <th className="px-3 py-2 text-left text-slate-600 font-medium">Detalle</th>
                  <th className="px-3 py-2 text-right text-slate-600 font-medium">Importe</th>
                </tr>
              </thead>
              <tbody>
                {retenciones.map((ret, idx) => (
                  <tr key={idx} className="border-t border-slate-200">
                    <td className="px-3 py-2">{ret.descConcepto ?? ret.codigoConcepto ?? "-"}</td>
                    <td className="px-3 py-2">{ret.detalleAclaratorio ?? "-"}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatCurrency(ret.importeRetencion)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div className="p-3 space-y-1">
        <DataRow label="Total Deducciones" value={formatCurrency(data["totalDeduccion"])} mono />
        <DataRow label="Total Retenciones" value={formatCurrency(data["totalRetencion"])} mono />
        <DataRow label="Total Retenciones AFIP" value={formatCurrency(data["totalRetencionAfip"])} mono />
        <DataRow label="Neto a Pagar" value={formatCurrency(data["totalNetoAPagar"])} mono />
        <DataRow label="Pago según condiciones" value={formatCurrency(data["totalPagoSegunCondicion"])} mono />
      </div>
    </div>
  );
}

function AjusteLimpiosSection({ data }: { data: Record<string, unknown> }) {
  // Extraer datos de crédito y débito
  const credito: Record<string, unknown> = {};
  const debito: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(data)) {
    if (key.startsWith("credito_")) credito[key.replace("credito_", "")] = val;
    if (key.startsWith("debito_")) debito[key.replace("debito_", "")] = val;
  }

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-300 p-4 rounded-lg">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">AJUSTE DE LIQUIDACION</h3>
            <p className="text-sm text-slate-600 mt-1">
              Tipo de operación: {descOrCode(data, "descTipoOperacion", "codTipoOperacion", "Desconocido")}
            </p>
            <p className="text-sm font-mono text-slate-700">
              C.O.E.: {String(data["coe"] ?? "-")}
            </p>
            {data["coeAjustado"] != null && Number(data["coeAjustado"]) !== 0 && (
              <p className="text-sm font-mono text-slate-700">
                COE Ajustado: {String(data["coeAjustado"])}
              </p>
            )}
          </div>
          <Badge variant="warning">Ajuste</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AjusteLadoSection data={credito} title="CREDITO" />
        <AjusteLadoSection data={debito} title="DEBITO" />
      </div>

      {/* Totales Unificados */}
      <div className="border border-slate-300 rounded">
        <SectionHeader title="TOTALES UNIFICADOS" />
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 p-4">
          <div className="space-y-2">
            <DataRow label="Subtotal Déb/Créd" value={formatCurrency(data["totales_subTotalDebCred"])} mono />
            <DataRow label="Base Deducciones" value={formatCurrency(data["totales_totalBaseDeducciones"])} mono />
            <DataRow label="Subtotal General" value={formatCurrency(data["totales_subTotalGeneral"])} mono />
            <DataRow label="IVA Deducciones" value={formatCurrency(data["totales_ivaDeducciones"])} mono />
          </div>
          <div className="space-y-2">
            <DataRow label="IVA 10.5%" value={formatCurrency(data["totales_iva105"])} mono />
            <DataRow label="IVA 21%" value={formatCurrency(data["totales_iva21"])} mono />
            <DataRow label="Ret. Ganancias" value={formatCurrency(data["totales_retencionesGanancias"])} mono />
            <DataRow label="Ret. IVA" value={formatCurrency(data["totales_retencionesIVA"])} mono />
          </div>
          <div className="space-y-2">
            <DataRow label="Otras Retenciones" value={formatCurrency(data["totales_importeOtrasRetenciones"])} mono />
            <DataRow label="IVA RG 4310/18" value={formatCurrency(data["totales_ivaRG4310_18"])} mono />
            <div className="bg-green-50 border border-green-200 rounded p-2 mt-2">
              <DataRow label="Importe Neto" value={formatCurrency(data["totales_importeNeto"])} mono />
              <DataRow label="Pago según condiciones" value={formatCurrency(data["totales_pagoSCondicion"])} mono />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function CoeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const coeId = Number(id);
  const [datosExpanded, setDatosExpanded] = useState(true);
  const [rawDataExpanded, setRawDataExpanded] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  const coeQuery = useCoeQuery(coeId);
  const coe = coeQuery.data;

  async function handleDownloadPdf() {
    if (!coe) return;
    setDownloadingPdf(true);
    try {
      const blob = await downloadCoePdf(coe.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `liquidacion_${coe.coe}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Error al descargar PDF");
    } finally {
      setDownloadingPdf(false);
    }
  }

  if (coeQuery.isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (coeQuery.isError || !coe) {
    return (
      <div>
        <PageHeader title="Error" />
        <Alert variant="error">COE no encontrado</Alert>
        <Button variant="secondary" onClick={() => navigate("/coes")} className="mt-4">
          Volver a COEs
        </Button>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={`COE: ${coe.coe ?? "Sin número"}`}
        subtitle={coe.taxpayer?.empresa}
        actions={
          <Button variant="secondary" onClick={() => navigate("/coes")}>
            Volver
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Información del Documento" />
          <dl className="grid grid-cols-3 gap-4">
            <div>
              <dt className="text-sm font-medium text-slate-500">COE</dt>
              <dd className="mt-1 font-mono text-slate-900">{coe.coe ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Estado ARCA</dt>
              <dd className="mt-1">
                <EstadoBadge estado={coe.estado} />
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Estado Ciclo</dt>
              <dd className="mt-1">
                <CoeEstadoBadge estado={coe.coe_estado?.estado ?? null} />
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Fecha Creación</dt>
              <dd className="mt-1 text-slate-900">
                {formatDateTime(coe.created_at)}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-500">Documento PDF</dt>
              <dd className="mt-1">
                <button
                  type="button"
                  onClick={() => void handleDownloadPdf()}
                  disabled={downloadingPdf}
                  className="inline-flex items-center rounded-md bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 ring-1 ring-inset ring-blue-200 hover:bg-blue-100 disabled:opacity-50"
                >
                  {downloadingPdf ? "Descargando..." : "Descargar PDF"}
                </button>
              </dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHeader title="Cliente" />
          {coe.taxpayer ? (
            <dl className="space-y-4">
              <div>
                <dt className="text-sm font-medium text-slate-500">Empresa</dt>
                <dd className="mt-1 text-slate-900">{coe.taxpayer.empresa}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-slate-500">CUIT</dt>
                <dd className="mt-1 font-mono text-slate-900">{coe.taxpayer.cuit}</dd>
              </div>
              <div className="pt-4 border-t border-slate-200">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/clientes/${coe.taxpayer!.id}`)}
                >
                  Ver cliente
                </Button>
              </div>
            </dl>
          ) : (
            <p className="text-slate-500">Cliente no disponible</p>
          )}
        </Card>

        {/* Datos - Colapsable */}
        {coe.raw_data ? (
          <Card className="lg:col-span-2">
            <button
              type="button"
              onClick={() => setDatosExpanded(!datosExpanded)}
              className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition-colors"
            >
              <h3 className="text-lg font-semibold text-slate-900">Datos</h3>
              <span className="text-slate-500 text-sm">
                {datosExpanded ? "▼ Colapsar" : "▶ Expandir"}
              </span>
            </button>
            {datosExpanded && (
              <div className="px-4 pb-4">
                {coe.tipo_documento === "AJUSTE" && coe.datos_limpios ? (
                  <AjusteLimpiosSection data={coe.datos_limpios} />
                ) : (
                  <DatosLimpiosSection rawData={coe.raw_data} datosLimpios={coe.datos_limpios} taxpayerId={coe.taxpayer_id} />
                )}
              </div>
            )}
          </Card>
        ) : null}

        {/* Datos Crudos - Colapsable */}
        {coe.raw_data ? (
          <Card className="lg:col-span-2">
            <button
              type="button"
              onClick={() => setRawDataExpanded(!rawDataExpanded)}
              className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition-colors"
            >
              <h3 className="text-lg font-semibold text-slate-900">Datos Crudos</h3>
              <span className="text-slate-500 text-sm">
                {rawDataExpanded ? "▼ Colapsar" : "▶ Expandir"}
              </span>
            </button>
            {rawDataExpanded && (
              <div className="px-4 pb-4">
                <pre className="bg-slate-50 p-4 rounded-lg text-xs overflow-x-auto">
                  {JSON.stringify(coe.raw_data, null, 2)}
                </pre>
              </div>
            )}
          </Card>
        ) : null}
      </div>
    </div>
  );
}
