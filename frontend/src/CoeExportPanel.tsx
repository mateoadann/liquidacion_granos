import { useState } from "react";
import type { Client, CoesExportFormat } from "./clients";

interface CoeExportPanelProps {
  client: Client;
  isDownloading: boolean;
  errorMessage: string | null;
  onDownload: (format: CoesExportFormat, filters: { fechaDesde?: string; fechaHasta?: string }) => Promise<void>;
  onBack: () => void;
}

export default function CoeExportPanel({
  client,
  isDownloading,
  errorMessage,
  onDownload,
  onBack,
}: CoeExportPanelProps) {
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");

  async function handleDownload(format: CoesExportFormat) {
    await onDownload(format, {
      fechaDesde: fechaDesde || undefined,
      fechaHasta: fechaHasta || undefined,
    });
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900">Exportar COEs</h2>
        <button
          type="button"
          onClick={onBack}
          className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm"
        >
          Volver
        </button>
      </div>

      <p className="mt-2 text-sm text-slate-600">
        Cliente: <span className="font-medium text-slate-900">{client.empresa}</span> ({client.cuit})
      </p>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="text-sm text-slate-700">
          Fecha desde (opcional)
          <input
            type="date"
            value={fechaDesde}
            onChange={(event) => setFechaDesde(event.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="text-sm text-slate-700">
          Fecha hasta (opcional)
          <input
            type="date"
            value={fechaHasta}
            onChange={(event) => setFechaHasta(event.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleDownload("csv")}
          disabled={isDownloading}
          className="rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700 disabled:opacity-50"
        >
          Descargar CSV
        </button>
        <button
          type="button"
          onClick={() => void handleDownload("xlsx")}
          disabled={isDownloading}
          className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 disabled:opacity-50"
        >
          Descargar XLSX
        </button>
      </div>

      {errorMessage ? (
        <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {errorMessage}
        </p>
      ) : null}
    </section>
  );
}
