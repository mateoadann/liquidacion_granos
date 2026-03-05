import { useState } from "react";
import { Button, Card, CardHeader, Input, Alert, Badge, Spinner } from "../ui";
import { useClientsQuery } from "../../hooks/useClients";
import { usePlaywrightJobQuery, useRunPlaywrightMutation } from "../../hooks/useClients";

function formatDate(date: Date): string {
  const day = date.getDate().toString().padStart(2, "0");
  const month = (date.getMonth() + 1).toString().padStart(2, "0");
  const year = date.getFullYear();
  return `${day}/${month}/${year}`;
}

function getDefaultDateRange() {
  const hasta = new Date();
  const desde = new Date();
  desde.setMonth(desde.getMonth() - 6);
  return {
    desde: desde.toISOString().split("T")[0],
    hasta: hasta.toISOString().split("T")[0],
  };
}

function JobStatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "success" | "warning" | "error" | "info"> = {
    pending: "warning",
    running: "info",
    completed: "success",
    failed: "error",
  };
  return <Badge variant={variants[status] ?? "default"}>{status}</Badge>;
}

export function PlaywrightPanel() {
  const defaults = getDefaultDateRange();
  const [fechaDesde, setFechaDesde] = useState(defaults.desde);
  const [fechaHasta, setFechaHasta] = useState(defaults.hasta);
  const [selectedClients, setSelectedClients] = useState<number[]>([]);
  const [currentJobId, setCurrentJobId] = useState<number | null>(null);

  const clientsQuery = useClientsQuery();
  const runMutation = useRunPlaywrightMutation();
  const jobQuery = usePlaywrightJobQuery(currentJobId);

  const activeClients = clientsQuery.data?.filter(
    (c) => c.activo && c.playwrightEnabled && c.claveFiscalCargada
  ) ?? [];

  const handleSelectAll = () => {
    if (selectedClients.length === activeClients.length) {
      setSelectedClients([]);
    } else {
      setSelectedClients(activeClients.map((c) => c.id));
    }
  };

  const handleToggleClient = (id: number) => {
    setSelectedClients((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleRun = async () => {
    if (selectedClients.length === 0) return;

    try {
      const result = await runMutation.mutateAsync({
        fechaDesde: formatDate(new Date(fechaDesde)),
        fechaHasta: formatDate(new Date(fechaHasta)),
        taxpayerIds: selectedClients,
      });
      setCurrentJobId(result.id);
    } catch {
      // Error handled by mutation
    }
  };

  const isRunning = jobQuery.data?.status === "pending" || jobQuery.data?.status === "running";
  const canRun = selectedClients.length > 0 && !runMutation.isPending && !isRunning;

  return (
    <Card padding="lg">
      <CardHeader
        title="Extracción de COEs"
        subtitle="Obtener documentos desde ARCA para los clientes seleccionados"
      />

      <div className="space-y-4">
        {/* Fechas */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Fecha desde"
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            disabled={isRunning}
          />
          <Input
            label="Fecha hasta"
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            disabled={isRunning}
          />
        </div>

        {/* Selección de clientes */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-slate-700">
              Clientes ({selectedClients.length} de {activeClients.length} seleccionados)
            </label>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSelectAll}
              disabled={isRunning}
            >
              {selectedClients.length === activeClients.length ? "Deseleccionar todos" : "Seleccionar todos"}
            </Button>
          </div>

          {clientsQuery.isLoading ? (
            <div className="flex justify-center py-4">
              <Spinner />
            </div>
          ) : activeClients.length === 0 ? (
            <Alert variant="warning">
              No hay clientes configurados para extracción automática
            </Alert>
          ) : (
            <div className="border border-slate-200 rounded-md max-h-48 overflow-y-auto">
              {activeClients.map((client) => (
                <label
                  key={client.id}
                  className="flex items-center px-3 py-2 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0"
                >
                  <input
                    type="checkbox"
                    checked={selectedClients.includes(client.id)}
                    onChange={() => handleToggleClient(client.id)}
                    disabled={isRunning}
                    className="h-4 w-4 text-green-600 rounded border-slate-300 focus:ring-green-500"
                  />
                  <span className="ml-3 text-sm text-slate-700">{client.empresa}</span>
                  <span className="ml-auto text-xs text-slate-400">{client.cuit}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Error */}
        {runMutation.isError ? (
          <Alert variant="error">
            {runMutation.error instanceof Error
              ? runMutation.error.message
              : "Error al iniciar extracción"}
          </Alert>
        ) : null}

        {/* Botón de ejecución */}
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={handleRun}
          disabled={!canRun}
          isLoading={runMutation.isPending}
        >
          {isRunning ? "Extracción en curso..." : "Iniciar Extracción"}
        </Button>

        {/* Estado del job */}
        {jobQuery.data ? (
          <div className="border-t border-slate-200 pt-4 mt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-slate-700">Estado del Job</span>
              <JobStatusBadge status={jobQuery.data.status} />
            </div>

            {jobQuery.data.status === "running" && jobQuery.data.progress ? (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-slate-600">
                  <span>Progreso</span>
                  <span>
                    {jobQuery.data.progress.completedClients} / {jobQuery.data.progress.totalClients}
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className="bg-green-600 h-2 rounded-full transition-all"
                    style={{
                      width: `${
                        (jobQuery.data.progress.completedClients /
                          jobQuery.data.progress.totalClients) *
                        100
                      }%`,
                    }}
                  />
                </div>
              </div>
            ) : null}

            {jobQuery.data.status === "completed" && jobQuery.data.result ? (
              <div className="text-sm text-slate-600 space-y-1">
                <p>Clientes procesados: {jobQuery.data.result.taxpayersTotal}</p>
                <p className="text-green-600">Exitosos: {jobQuery.data.result.taxpayersOk}</p>
                {jobQuery.data.result.taxpayersError > 0 ? (
                  <p className="text-red-600">Con errores: {jobQuery.data.result.taxpayersError}</p>
                ) : null}
              </div>
            ) : null}

            {jobQuery.data.status === "failed" ? (
              <Alert variant="error">
                {jobQuery.data.errorMessage ?? "Error desconocido"}
              </Alert>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
