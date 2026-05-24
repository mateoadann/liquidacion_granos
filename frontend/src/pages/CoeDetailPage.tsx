import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/layout";
import { Card, CardHeader, Badge, Button, Spinner, Alert, ConfirmModal } from "../components/ui";
import { useCoeQuery, useToggleCoeControladaMutation } from "../hooks/useCoes";
import { downloadCoePdf } from "../api/coes";
import { formatDateTime } from "../dateUtils";
import {
  DatosLimpiosSection,
  AjusteLimpiosSection,
} from "../components/coes/dataDisplay";

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

export function CoeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const coeId = Number(id);
  const [datosExpanded, setDatosExpanded] = useState(true);
  const [rawDataExpanded, setRawDataExpanded] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [confirmUncheckOpen, setConfirmUncheckOpen] = useState(false);

  const coeQuery = useCoeQuery(coeId);
  const coe = coeQuery.data;
  const toggleMutation = useToggleCoeControladaMutation();

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
            <div className="col-span-3">
              <dt className="text-sm font-medium text-slate-500">Control</dt>
              <dd className="mt-1 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={coe.controlada}
                  onChange={(e) => {
                    if (e.target.checked) {
                      toggleMutation.mutate({ id: coe.id, controlada: true });
                    } else {
                      setConfirmUncheckOpen(true);
                    }
                  }}
                  disabled={toggleMutation.isPending}
                  aria-label="Marcar como controlada"
                  className="form-checkbox h-4 w-4 rounded border-slate-300 text-green-600 focus:ring-green-500 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                />
                {coe.controlada && (
                  <span className="text-sm text-slate-700 whitespace-nowrap">
                    {`Controlada por ${coe.controlada_por_nombre ?? coe.controlada_por ?? "—"} el ${formatDateTime(coe.controlada_en)}`}
                  </span>
                )}
              </dd>
              {toggleMutation.isError && (
                <Alert variant="error" className="mt-2">
                  {toggleMutation.error instanceof Error
                    ? toggleMutation.error.message
                    : "Error al actualizar controlada"}
                </Alert>
              )}
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
      <ConfirmModal
        isOpen={confirmUncheckOpen}
        onClose={() => setConfirmUncheckOpen(false)}
        onConfirm={() => {
          toggleMutation.mutate(
            { id: coe.id, controlada: false },
            { onSettled: () => setConfirmUncheckOpen(false) },
          );
        }}
        title="Desmarcar control"
        message="Vas a desmarcar esta liquidación como controlada. Se perderá el registro de quién la controló. ¿Confirmás?"
        confirmLabel="Desmarcar"
        cancelLabel="Cancelar"
        variant="danger"
        isLoading={toggleMutation.isPending}
      />
    </div>
  );
}
