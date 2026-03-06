import { useState } from "react";
import { PageHeader } from "../components/layout";
import { Card, Button, Spinner, Alert } from "../components/ui";
import { useClientsQuery, useDownloadClientCoesMutation } from "../useClients";

type Step = 1 | 2 | 3;

export function ExportPage() {
  const [step, setStep] = useState<Step>(1);
  const [selectedClients, setSelectedClients] = useState<number[]>([]);
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [formato, setFormato] = useState<"csv" | "xlsx">("csv");
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportSuccess, setExportSuccess] = useState(false);

  const clientsQuery = useClientsQuery();
  const downloadMutation = useDownloadClientCoesMutation();

  const clients = clientsQuery.data ?? [];
  const activeClients = clients.filter((c) => c.activo);

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
      // Exportar cada cliente seleccionado
      for (const clientId of selectedClients) {
        await downloadMutation.mutateAsync({
          clientId,
          fechaDesde: fechaDesde || undefined,
          fechaHasta: fechaHasta || undefined,
          format: formato,
        });
      }
      setExportSuccess(true);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Error al exportar");
    }
  }

  function resetWizard() {
    setStep(1);
    setSelectedClients([]);
    setFechaDesde("");
    setFechaHasta("");
    setFormato("csv");
    setExportError(null);
    setExportSuccess(false);
  }

  return (
    <div>
      <PageHeader
        title="Exportar COEs"
        subtitle="Descarga COEs en formato CSV o Excel"
      />

      {/* Progress Steps */}
      <div className="flex items-center justify-center mb-8">
        {[1, 2, 3].map((s) => (
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
            {s < 3 && (
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
        {/* Step 1: Seleccionar clientes */}
        {step === 1 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 1: Seleccionar clientes
            </h3>

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
                disabled={selectedClients.length === 0}
              >
                Siguiente
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Rango de fechas */}
        {step === 2 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 2: Rango de fechas (opcional)
            </h3>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Desde
                </label>
                <input
                  type="date"
                  value={fechaDesde}
                  onChange={(e) => setFechaDesde(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Hasta
                </label>
                <input
                  type="date"
                  value={fechaHasta}
                  onChange={(e) => setFechaHasta(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
            </div>

            <p className="mt-4 text-sm text-slate-500">
              Dejar vacío para exportar todas las fechas
            </p>

            <div className="flex justify-between mt-6">
              <Button variant="secondary" onClick={() => setStep(1)}>
                Anterior
              </Button>
              <Button onClick={() => setStep(3)}>Siguiente</Button>
            </div>
          </div>
        )}

        {/* Step 3: Formato y confirmación */}
        {step === 3 && (
          <div className="p-6">
            <h3 className="text-lg font-medium text-slate-900 mb-4">
              Paso 3: Formato y confirmación
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
                <div className="mb-6">
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Formato de exportación
                  </label>
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="formato"
                        value="csv"
                        checked={formato === "csv"}
                        onChange={() => setFormato("csv")}
                        className="h-4 w-4 text-green-600"
                      />
                      <span className="text-sm">CSV</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="formato"
                        value="xlsx"
                        checked={formato === "xlsx"}
                        onChange={() => setFormato("xlsx")}
                        className="h-4 w-4 text-green-600"
                      />
                      <span className="text-sm">Excel (.xlsx)</span>
                    </label>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-lg p-4 mb-6">
                  <h4 className="text-sm font-medium text-slate-900 mb-2">Resumen</h4>
                  <dl className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Clientes:</dt>
                      <dd className="text-slate-900">{selectedClients.length}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Período:</dt>
                      <dd className="text-slate-900">
                        {fechaDesde && fechaHasta
                          ? `${fechaDesde} a ${fechaHasta}`
                          : fechaDesde
                          ? `Desde ${fechaDesde}`
                          : fechaHasta
                          ? `Hasta ${fechaHasta}`
                          : "Todas las fechas"}
                      </dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Formato:</dt>
                      <dd className="text-slate-900">{formato.toUpperCase()}</dd>
                    </div>
                  </dl>
                </div>

                {exportError && (
                  <Alert variant="error" className="mb-4">
                    {exportError}
                  </Alert>
                )}

                <div className="flex justify-between">
                  <Button variant="secondary" onClick={() => setStep(2)}>
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
