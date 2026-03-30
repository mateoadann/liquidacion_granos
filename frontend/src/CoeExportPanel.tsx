import { useState } from "react";
import type { Client } from "./clients";

/**
 * Return "YYYY-MM" for the previous calendar month relative to `now`.
 */
function getPreviousMonthValue(now = new Date()): string {
  const year = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
  const month = now.getMonth() === 0 ? 12 : now.getMonth(); // 1-indexed
  return `${year}-${String(month).padStart(2, "0")}`;
}

/**
 * Given "YYYY-MM", return { first: "YYYY-MM-01", last: "YYYY-MM-DD" }.
 */
function monthBounds(monthValue: string): { first: string; last: string } {
  const [yearStr, monthStr] = monthValue.split("-");
  const year = Number(yearStr);
  const month = Number(monthStr);
  const first = `${year}-${String(month).padStart(2, "0")}-01`;
  const lastDay = new Date(year, month, 0).getDate();
  const last = `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
  return { first, last };
}

interface CoeExportPanelProps {
  client: Client;
  isDownloading: boolean;
  errorMessage: string | null;
  onDownload: (filters: { fechaDesde?: string; fechaHasta?: string }) => Promise<void>;
  onBack: () => void;
}

export default function CoeExportPanel({
  client,
  isDownloading,
  errorMessage,
  onDownload,
  onBack,
}: CoeExportPanelProps) {
  const [selectedMonth, setSelectedMonth] = useState(getPreviousMonthValue);

  const { first, last } = monthBounds(selectedMonth);

  async function handleDownload() {
    await onDownload({ fechaDesde: first, fechaHasta: last });
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

      <div className="mt-4">
        <label className="block text-sm font-medium text-slate-700 mb-1">
          Mes a exportar
        </label>
        <input
          type="month"
          value={selectedMonth}
          onChange={(e) => setSelectedMonth(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm md:w-64"
        />
        <p className="mt-1 text-xs text-slate-500">
          Período: {first} a {last}
        </p>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleDownload()}
          disabled={isDownloading || !selectedMonth}
          className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 disabled:opacity-50"
        >
          {isDownloading ? "Descargando..." : "Descargar XLSX"}
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
