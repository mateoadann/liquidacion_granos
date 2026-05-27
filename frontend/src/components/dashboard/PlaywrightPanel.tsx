import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  CardHeader,
  DatePicker,
  Drawer,
  SearchInput,
  Spinner,
} from "../ui";
import { useClientsQuery } from "../../hooks/useClients";
import { useRunPlaywrightMutation } from "../../hooks/useClients";
import type { Client } from "../../clients";
import { matchesClientQuery, normalizeClientQuery } from "./clientFilter";

const INLINE_CHIPS_LIMIT = 3;

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

interface SelectedChipProps {
  client: Client;
  onRemove: (id: number) => void;
}

function SelectedChip({ client, onRemove }: SelectedChipProps) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-green-50 text-green-800 ring-1 ring-inset ring-green-200 px-2.5 py-1 text-xs font-medium">
      <span className="truncate max-w-[180px]" title={client.empresa}>
        {client.empresa}
      </span>
      <button
        type="button"
        onClick={() => onRemove(client.id)}
        className="text-green-700 hover:text-green-900 focus:outline-none"
        aria-label={`Quitar ${client.empresa}`}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2.5}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </span>
  );
}

export function PlaywrightPanel() {
  const defaults = getDefaultDateRange();
  const [fechaDesde, setFechaDesde] = useState(defaults.desde);
  const [fechaHasta, setFechaHasta] = useState(defaults.hasta);
  const [selectedClients, setSelectedClients] = useState<number[]>([]);
  const [search, setSearch] = useState("");
  const [isSelectedDrawerOpen, setIsSelectedDrawerOpen] = useState(false);
  const [lastEnqueued, setLastEnqueued] = useState<number | null>(null);

  const clientsQuery = useClientsQuery();
  const runMutation = useRunPlaywrightMutation();

  const activeClients = useMemo(
    () =>
      (clientsQuery.data ?? []).filter(
        (c) => c.activo && c.playwrightEnabled && c.claveFiscalCargada,
      ),
    [clientsQuery.data],
  );

  const normalizedQuery = normalizeClientQuery(search);
  const filteredClients = useMemo(
    () => activeClients.filter((c) => matchesClientQuery(c, normalizedQuery)),
    [activeClients, normalizedQuery],
  );

  const selectedSet = useMemo(() => new Set(selectedClients), [selectedClients]);
  const selectedClientObjects = useMemo(
    () => activeClients.filter((c) => selectedSet.has(c.id)),
    [activeClients, selectedSet],
  );

  const allFilteredSelected =
    filteredClients.length > 0 &&
    filteredClients.every((c) => selectedSet.has(c.id));

  const handleToggleFiltered = () => {
    if (filteredClients.length === 0) return;
    setSelectedClients((prev) => {
      const prevSet = new Set(prev);
      if (allFilteredSelected) {
        for (const c of filteredClients) prevSet.delete(c.id);
      } else {
        for (const c of filteredClients) prevSet.add(c.id);
      }
      return Array.from(prevSet);
    });
  };

  const handleToggleClient = (id: number) => {
    setSelectedClients((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleClearSelection = () => setSelectedClients([]);

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
      setSearch("");
    } catch {
      // Error handled by mutation
    }
  };

  const canRun = selectedClients.length > 0 && !runMutation.isPending;
  const selectedCount = selectedClients.length;
  const inlineChips = selectedClientObjects.slice(0, INLINE_CHIPS_LIMIT);
  const hiddenChipsCount = Math.max(0, selectedCount - INLINE_CHIPS_LIMIT);

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
              Empresas ({selectedCount} de {activeClients.length} seleccionadas)
            </label>
            {selectedCount > 0 ? (
              <Button variant="ghost" size="sm" onClick={handleClearSelection}>
                Limpiar selección
              </Button>
            ) : null}
          </div>

          {selectedCount > 0 ? (
            <div className="mb-2 flex flex-wrap items-center gap-1.5 rounded-md border border-green-100 bg-green-50/40 px-2 py-1.5">
              {inlineChips.map((c) => (
                <SelectedChip key={c.id} client={c} onRemove={handleToggleClient} />
              ))}
              {hiddenChipsCount > 0 ? (
                <button
                  type="button"
                  onClick={() => setIsSelectedDrawerOpen(true)}
                  className="text-xs font-medium text-green-700 hover:text-green-900 underline underline-offset-2"
                >
                  + {hiddenChipsCount} más → Ver seleccionadas
                </button>
              ) : selectedCount > 0 ? (
                <button
                  type="button"
                  onClick={() => setIsSelectedDrawerOpen(true)}
                  className="text-xs font-medium text-green-700 hover:text-green-900 underline underline-offset-2"
                >
                  Ver seleccionadas
                </button>
              ) : null}
            </div>
          ) : null}

          {clientsQuery.isLoading ? (
            <div className="flex justify-center py-4">
              <Spinner />
            </div>
          ) : activeClients.length === 0 ? (
            <Alert variant="warning">
              No hay empresas configuradas para consultar Arca.
            </Alert>
          ) : (
            <>
              <div className="mb-2 flex items-center gap-2">
                <div className="flex-1">
                  <SearchInput
                    value={search}
                    onChange={setSearch}
                    placeholder="Buscar por empresa, CUIT o representado..."
                  />
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleToggleFiltered}
                  disabled={filteredClients.length === 0}
                >
                  {allFilteredSelected ? "Deseleccionar" : "Seleccionar"}
                  {normalizedQuery ? " visibles" : " todos"}
                </Button>
              </div>

              {filteredClients.length === 0 ? (
                <div className="rounded-md border border-slate-200 px-3 py-6 text-center text-sm text-slate-500">
                  No se encontraron empresas para "{search}".
                </div>
              ) : (
                <div className="border border-slate-200 rounded-md max-h-48 overflow-y-auto">
                  {filteredClients.map((client) => (
                    <label
                      key={client.id}
                      className="flex items-center px-3 py-2 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0"
                    >
                      <input
                        type="checkbox"
                        checked={selectedSet.has(client.id)}
                        onChange={() => handleToggleClient(client.id)}
                        className="h-4 w-4 text-green-600 rounded border-slate-300 focus:ring-green-500"
                      />
                      <span className="ml-3 text-sm text-slate-700 flex-1 truncate">
                        {client.empresa}
                      </span>
                      <span className="ml-auto text-xs text-slate-400 font-mono">
                        {client.cuit}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </>
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

      <Drawer
        isOpen={isSelectedDrawerOpen}
        onClose={() => setIsSelectedDrawerOpen(false)}
        title={`Empresas seleccionadas (${selectedCount})`}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={handleClearSelection}
              disabled={selectedCount === 0}
            >
              Limpiar selección
            </Button>
            <Button variant="primary" onClick={() => setIsSelectedDrawerOpen(false)}>
              Cerrar
            </Button>
          </>
        }
      >
        {selectedCount === 0 ? (
          <p className="text-sm text-slate-500">No hay empresas seleccionadas.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {selectedClientObjects.map((c) => (
              <li key={c.id} className="flex items-center justify-between py-2.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900 truncate">
                    {c.empresa}
                  </p>
                  <p className="text-xs text-slate-500 font-mono">{c.cuit}</p>
                </div>
                <button
                  type="button"
                  onClick={() => handleToggleClient(c.id)}
                  className="ml-3 inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                >
                  Quitar
                </button>
              </li>
            ))}
          </ul>
        )}
      </Drawer>
    </Card>
  );
}
