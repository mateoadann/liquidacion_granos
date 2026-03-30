import { useState } from "react";
import { PageHeader } from "../components/layout";
import { Card, Button, Spinner, Alert } from "../components/ui";
import { useClientsQuery, useDownloadClientCoesMutation } from "../useClients";

type Step = 1 | 2;

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

/**
 * Format "YYYY-MM-DD" as "DD/MM/AAAA" for display.
 */
function formatDateDisplay(isoDate: string): string {
  const [y, m, d] = isoDate.split("-");
  return `${d}/${m}/${y}`;
}

/**
 * Format "YYYY-MM" as a human-friendly label, e.g. "Febrero 2026".
 */
function formatMonthLabel(monthValue: string): string {
  const MONTH_NAMES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
  ];
  const [yearStr, monthStr] = monthValue.split("-");
  const monthIndex = Number(monthStr) - 1;
  return `${MONTH_NAMES[monthIndex] ?? monthStr} ${yearStr}`;
}

export function ExportPage() {
  const [step, setStep] = useState<Step>(1);
  const [selectedClients, setSelectedClients] = useState<number[]>([]);
  const [selectedMonth, setSelectedMonth] = useState(getPreviousMonthValue);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportSuccess, setExportSuccess] = useState(false);

  const clientsQuery = useClientsQuery();
  const downloadMutation = useDownloadClientCoesMutation();

  const clients = clientsQuery.data ?? [];
  const activeClients = clients.filter((c) => c.activo);

  const { first: fechaDesde, last: fechaHasta } = monthBounds(selectedMonth);

  function toggleClient(clientId: number) {
    setSelectedClients((prev) =>
      prev.includes(clientId)
        ? prev.filter((id) => id !== clientId)
        : [...prev, clientId]
    );
  }

  function selectAll() {
    setSelectedClients(activeClients.map((c) => c.id));
  }

  function selectNone() {
    setSelectedClients([]);
  }

  async function handleExport() {
    if (selectedClients.length === 0) return;

    setExportError(null);
    setExportSuccess(false);

    try {
      for (const clientId of selectedClients) {
        const result = await downloadMutation.mutateAsync({
          clientId,
          fechaDesde,
          fechaHasta,
        });

        const url = URL.createObjectURL(result.blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = result.fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
      setExportSuccess(true);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Error al exportar");
    }
  }

  function resetWizard() {
    setStep(1);
    setSelectedClients([]);
    setSelectedMonth(getPreviousMonthValue());
    setExportError(null);
    setExportSuccess(false);
  }

  return (
    <div>
      <PageHeader
        title="Exportar COEs"
        subtitle="Descarga COEs en formato Excel (.xlsx)"
      />

      {/* Progress Steps */}
      <div className="flex items-center justify-center mb-8">
        {[1, 2].map((s) => (
          <div key={s} className="flex items-center">
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center font-medium ${
                step >= s
                  ? "bg-green-600 text-white"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              {s}
            </div>
            {s < 2 && (
              <div
                className={`w-20 h-1 ${
                  step > s ? "bg-green-600" : "bg-slate-200"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      <Card className="max-w-2xl mx-auto">
        {/* Step 1: Seleccionar clientes y mes */}
        {step === 1 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 1: Seleccionar clientes y período
            </h3>

            {/* Month selector */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Mes a exportar
              </label>
              <input
                type="month"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm md:w-64"
              />
              <p className="mt-1 text-xs text-slate-500">
                Período: {formatDateDisplay(fechaDesde)} a {formatDateDisplay(fechaHasta)}
              </p>
            </div>

            {/* Client list */}
            {clientsQuery.isLoading ? (
              <div className="flex justify-center py-8">
                <Spinner size="lg" />
              </div>
            ) : activeClients.length === 0 ? (
              <Alert variant="warning">No hay clientes activos</Alert>
            ) : (
              <>
                <div className="flex gap-2 mb-4">
                  <Button variant="ghost" size="sm" onClick={selectAll}>
                    Seleccionar todos
                  </Button>
                  <Button variant="ghost" size="sm" onClick={selectNone}>
                    Deseleccionar todos
                  </Button>
                </div>

                <div className="space-y-2 max-h-64 overflow-y-auto border border-slate-200 rounded-lg p-2">
                  {activeClients.map((client) => (
                    <label
                      key={client.id}
                      className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedClients.includes(client.id)}
                        onChange={() => toggleClient(client.id)}
                        className="h-4 w-4 text-green-600 rounded border-slate-300"
                      />
                      <span className="text-sm text-slate-900">{client.empresa}</span>
                      <span className="text-xs text-slate-500 font-mono">
                        {client.cuit}
                      </span>
                    </label>
                  ))}
                </div>

                <p className="mt-4 text-sm text-slate-500">
                  {selectedClients.length} cliente(s) seleccionado(s)
                </p>
              </>
            )}

            <div className="flex justify-end mt-6">
              <Button
                onClick={() => setStep(2)}
                disabled={selectedClients.length === 0 || !selectedMonth}
              >
                Siguiente
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Confirmación y exportación */}
        {step === 2 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 2: Confirmación
            </h3>

            {exportSuccess ? (
              <div className="text-center py-8">
                <div className="text-green-600 text-5xl mb-4">✓</div>
                <p className="text-lg font-medium text-slate-900 mb-2">
                  Exportación completada
                </p>
                <p className="text-sm text-slate-500 mb-6">
                  Los archivos se han descargado correctamente
                </p>
                <Button onClick={resetWizard}>Nueva exportación</Button>
              </div>
            ) : (
              <>
                <div className="bg-slate-50 rounded-lg p-4 mb-6">
                  <h4 className="text-sm font-medium text-slate-900 mb-2">Resumen</h4>
                  <dl className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Clientes:</dt>
                      <dd className="text-slate-900">{selectedClients.length}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Período:</dt>
                      <dd className="text-slate-900">{formatMonthLabel(selectedMonth)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Fechas:</dt>
                      <dd className="text-slate-900">{formatDateDisplay(fechaDesde)} a {formatDateDisplay(fechaHasta)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Formato:</dt>
                      <dd className="text-slate-900">Excel (.xlsx)</dd>
                    </div>
                  </dl>
                </div>

                {exportError && (
                  <Alert variant="error" className="mb-4">
                    {exportError}
                  </Alert>
                )}

                <div className="flex justify-between">
                  <Button variant="secondary" onClick={() => setStep(1)}>
                    Anterior
                  </Button>
                  <Button
                    onClick={handleExport}
                    isLoading={downloadMutation.isPending}
                  >
                    Exportar
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
