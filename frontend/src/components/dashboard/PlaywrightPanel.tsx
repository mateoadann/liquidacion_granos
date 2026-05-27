import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, Card, CardHeader, DatePicker, Alert, Spinner } from "../ui";
import { useClientsQuery } from "../../hooks/useClients";
import { useRunPlaywrightMutation } from "../../hooks/useClients";

function isoToArgDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function toIsoLocal(date: Date): string {
  const y = date.getFullYear();
  const m = (date.getMonth() + 1).toString().padStart(2, "0");
  const d = date.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function getDefaultDateRange() {
  const hasta = new Date();
  const desde = new Date();
  desde.setDate(desde.getDate() - 30);
  return {
    desde: toIsoLocal(desde),
    hasta: toIsoLocal(hasta),
  };
}

export function PlaywrightPanel() {
  const defaults = getDefaultDateRange();
  const [fechaDesde, setFechaDesde] = useState(defaults.desde);
  const [fechaHasta, setFechaHasta] = useState(defaults.hasta);
  const [selectedClients, setSelectedClients] = useState<number[]>([]);
  const [lastEnqueued, setLastEnqueued] = useState<number | null>(null);

  const clientsQuery = useClientsQuery();
  const runMutation = useRunPlaywrightMutation();

  const activeClients = clientsQuery.data?.filter(
    (c) => c.activo && c.playwrightEnabled && c.claveFiscalCargada,
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
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleRun = async () => {
    if (selectedClients.length === 0) return;
    setLastEnqueued(null);
    try {
      const jobs = await runMutation.mutateAsync({
        fechaDesde: isoToArgDate(fechaDesde),
        fechaHasta: isoToArgDate(fechaHasta),
        taxpayerIds: selectedClients,
      });
      setLastEnqueued(jobs.length);
      setSelectedClients([]);
    } catch {
      // Error handled by mutation
    }
  };

  const canRun = selectedClients.length > 0 && !runMutation.isPending;

  return (
    <Card padding="lg">
      <CardHeader
        title="Consulta de liquidaciones"
        subtitle="Descargar liquidaciones desde Arca para las empresas seleccionadas"
      />

      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <DatePicker label="Fecha desde" value={fechaDesde} onChange={setFechaDesde} />
          <DatePicker label="Fecha hasta" value={fechaHasta} onChange={setFechaHasta} />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-slate-700">
              Empresas ({selectedClients.length} de {activeClients.length} seleccionadas)
            </label>
            <Button variant="ghost" size="sm" onClick={handleSelectAll}>
              {selectedClients.length === activeClients.length
                ? "Deseleccionar todos"
                : "Seleccionar todos"}
            </Button>
          </div>

          {clientsQuery.isLoading ? (
            <div className="flex justify-center py-4">
              <Spinner />
            </div>
          ) : activeClients.length === 0 ? (
            <Alert variant="warning">
              No hay empresas configuradas para consultar Arca.
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
                    className="h-4 w-4 text-green-600 rounded border-slate-300 focus:ring-green-500"
                  />
                  <span className="ml-3 text-sm text-slate-700">{client.empresa}</span>
                  <span className="ml-auto text-xs text-slate-400">{client.cuit}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {runMutation.isError ? (
          <Alert variant="error">
            {runMutation.error instanceof Error
              ? runMutation.error.message
              : "No se pudo iniciar la consulta."}
          </Alert>
        ) : null}

        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={handleRun}
          disabled={!canRun}
          isLoading={runMutation.isPending}
        >
          Iniciar consulta
        </Button>

        {lastEnqueued !== null && lastEnqueued > 0 ? (
          <Alert variant="success">
            {lastEnqueued} extracción{lastEnqueued === 1 ? "" : "es"} encolada
            {lastEnqueued === 1 ? "" : "s"}.{" "}
            <Link to="/extracciones" className="underline font-medium">
              Ver detalle en /extracciones →
            </Link>
          </Alert>
        ) : null}
      </div>
    </Card>
  );
}
