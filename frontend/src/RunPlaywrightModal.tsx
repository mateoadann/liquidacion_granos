import { useEffect, useMemo, useState } from "react";
import type { Client, RunPlaywrightPipelineInput } from "./clients";

interface RunPlaywrightModalProps {
  isOpen: boolean;
  clients: Client[];
  isSubmitting: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onSubmit: (input: RunPlaywrightPipelineInput) => Promise<void> | void;
}

function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function todayIso(): string {
  return toIsoDate(new Date());
}

function sixMonthsAgoIso(): string {
  const date = new Date();
  date.setMonth(date.getMonth() - 6);
  return toIsoDate(date);
}

function isoToArgDate(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

export default function RunPlaywrightModal({
  isOpen,
  clients,
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: RunPlaywrightModalProps) {
  const eligibleClients = useMemo(
    () => clients.filter((client) => client.activo && client.playwrightEnabled),
    [clients]
  );

  const [fechaDesde, setFechaDesde] = useState(sixMonthsAgoIso());
  const [fechaHasta, setFechaHasta] = useState(todayIso());
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    setFechaDesde(sixMonthsAgoIso());
    setFechaHasta(todayIso());
    setSelectedIds(eligibleClients.map((item) => item.id));
  }, [isOpen, eligibleClients]);

  if (!isOpen) return null;

  const hasSelection = selectedIds.length > 0;
  const canSubmit = Boolean(fechaDesde && fechaHasta && hasSelection && !isSubmitting);

  function toggleClient(clientId: number) {
    setSelectedIds((current) =>
      current.includes(clientId)
        ? current.filter((id) => id !== clientId)
        : [...current, clientId]
    );
  }

  function selectAll() {
    setSelectedIds(eligibleClients.map((item) => item.id));
  }

  function clearAll() {
    setSelectedIds([]);
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    await onSubmit({
      fechaDesde: isoToArgDate(fechaDesde),
      fechaHasta: isoToArgDate(fechaHasta),
      taxpayerIds: selectedIds,
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">
              Ejecutar proceso Playwright LPG
            </h3>
            <p className="mt-1 text-sm text-slate-600">
              Seleccioná clientes y rango de fechas. El seguimiento detallado se ve en logs del
              worker.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          >
            Cerrar
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="text-sm text-slate-700">
            Fecha desde
            <input
              type="date"
              value={fechaDesde}
              onChange={(event) => setFechaDesde(event.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="text-sm text-slate-700">
            Fecha hasta
            <input
              type="date"
              value={fechaHasta}
              onChange={(event) => setFechaHasta(event.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
            />
          </label>
        </div>

        <div className="mt-4 rounded-md border border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-sm font-medium text-slate-700">
              Clientes ({selectedIds.length}/{eligibleClients.length})
            </p>
            <div className="flex gap-2 text-xs">
              <button
                type="button"
                onClick={selectAll}
                className="rounded border border-slate-300 bg-white px-2 py-1"
              >
                Todos
              </button>
              <button
                type="button"
                onClick={clearAll}
                className="rounded border border-slate-300 bg-white px-2 py-1"
              >
                Ninguno
              </button>
            </div>
          </div>
          <div className="max-h-64 overflow-y-auto px-3 py-2">
            {eligibleClients.length === 0 ? (
              <p className="text-sm text-slate-500">
                No hay clientes activos con Playwright habilitado.
              </p>
            ) : (
              <ul className="space-y-2">
                {eligibleClients.map((client) => (
                  <li key={client.id}>
                    <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(client.id)}
                        onChange={() => toggleClient(client.id)}
                      />
                      <span>
                        <span className="font-medium">{client.empresa}</span>{" "}
                        <span className="text-slate-500">({client.cuit})</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {errorMessage ? (
          <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {errorMessage}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {isSubmitting ? "Ejecutando..." : "Ejecutar"}
          </button>
        </div>
      </div>
    </div>
  );
}
