import { useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Modal, SearchInput } from "../ui";
import { useBulkUpdateSchedulerMutation } from "../../hooks/useScheduler";
import type { BulkSchedulerConfig } from "../../api/scheduler";
import type { Client } from "../../clients";

interface DiaOption {
  value: string;
  label: string;
}

const DIAS_SEMANA: DiaOption[] = [
  { value: "lun", label: "Lun" },
  { value: "mar", label: "Mar" },
  { value: "mie", label: "Mié" },
  { value: "jue", label: "Jue" },
  { value: "vie", label: "Vie" },
  { value: "sab", label: "Sáb" },
  { value: "dom", label: "Dom" },
];

const HORA_LOCAL_REGEX = /^([01]\d|2[0-3]):[0-5]\d$/;
const DIAS_EXTRACCION_PRESETS: number[] = [10, 30, 60];
const DIAS_EXTRACCION_MIN = 1;
const DIAS_EXTRACCION_MAX = 366;

type QuickFilter = "todas" | "playwright_enabled" | "scheduler_inactivo";

interface BulkSchedulerModalProps {
  isOpen: boolean;
  onClose: () => void;
  clients: Client[];
  onSuccess?: (message: string) => void;
  onError?: (message: string) => void;
}

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string" && err.trim()) return err;
  return fallback;
}

export function BulkSchedulerModal({
  isOpen,
  onClose,
  clients,
  onSuccess,
  onError,
}: BulkSchedulerModalProps) {
  const mutation = useBulkUpdateSchedulerMutation();

  // Selector de empresas
  const [search, setSearch] = useState("");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("todas");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Toggles "aplicar este campo"
  const [applyActivo, setApplyActivo] = useState(false);
  const [applyDias, setApplyDias] = useState(false);
  const [applyHora, setApplyHora] = useState(false);
  const [applyDiasExtraccion, setApplyDiasExtraccion] = useState(false);

  // Valores config compartida
  const [activo, setActivo] = useState(true);
  const [diasSemana, setDiasSemana] = useState<string[]>([
    "lun",
    "mar",
    "mie",
    "jue",
    "vie",
  ]);
  const [horaLocal, setHoraLocal] = useState("06:00");
  const [diasExtraccion, setDiasExtraccion] = useState(30);
  const [diasExtraccionRaw, setDiasExtraccionRaw] = useState("30");

  const [error, setError] = useState<string | null>(null);

  // Reset al cerrar/abrir
  useEffect(() => {
    if (!isOpen) {
      setSearch("");
      setQuickFilter("todas");
      setSelectedIds(new Set());
      setApplyActivo(false);
      setApplyDias(false);
      setApplyHora(false);
      setApplyDiasExtraccion(false);
      setActivo(true);
      setDiasSemana(["lun", "mar", "mie", "jue", "vie"]);
      setHoraLocal("06:00");
      setDiasExtraccion(30);
      setDiasExtraccionRaw("30");
      setError(null);
    }
  }, [isOpen]);

  const filteredClients = useMemo(() => {
    const q = search.trim().toLowerCase();
    return clients.filter((c) => {
      if (!c.activo) return false;
      if (quickFilter === "playwright_enabled" && !c.playwrightEnabled) return false;
      if (quickFilter === "scheduler_inactivo" && c.schedulerActivo) return false;
      if (q && !c.empresa.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [clients, search, quickFilter]);

  const allVisibleSelected =
    filteredClients.length > 0 &&
    filteredClients.every((c) => selectedIds.has(c.id));

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        filteredClients.forEach((c) => next.delete(c.id));
      } else {
        filteredClients.forEach((c) => next.add(c.id));
      }
      return next;
    });
  }

  function toggleDia(value: string) {
    setDiasSemana((prev) =>
      prev.includes(value) ? prev.filter((d) => d !== value) : [...prev, value],
    );
  }

  const horaInvalida = applyHora && !HORA_LOCAL_REGEX.test(horaLocal);
  const diasExtraccionInvalido =
    applyDiasExtraccion &&
    (!Number.isInteger(diasExtraccion) ||
      diasExtraccion < DIAS_EXTRACCION_MIN ||
      diasExtraccion > DIAS_EXTRACCION_MAX);

  const algunCampoMarcado =
    applyActivo || applyDias || applyHora || applyDiasExtraccion;
  const seleccionVacia = selectedIds.size === 0;

  const canSubmit =
    !seleccionVacia &&
    algunCampoMarcado &&
    !horaInvalida &&
    !diasExtraccionInvalido &&
    !mutation.isPending;

  async function handleApply() {
    setError(null);

    if (applyDias && diasSemana.length === 0) {
      setError("Seleccioná al menos un día de la semana o desmarcá ese campo.");
      return;
    }

    const config: BulkSchedulerConfig = {};
    if (applyActivo) config.activo = activo;
    if (applyDias) {
      const orderedDias = DIAS_SEMANA.filter((d) => diasSemana.includes(d.value)).map(
        (d) => d.value,
      );
      config.dias_semana = orderedDias;
    }
    if (applyHora) config.hora_local = horaLocal;
    if (applyDiasExtraccion) config.dias_extraccion = diasExtraccion;

    try {
      const result = await mutation.mutateAsync({
        taxpayerIds: Array.from(selectedIds),
        config,
      });
      const msg = `Actualizadas ${result.actualizados} empresa(s).`;
      onSuccess?.(msg);
      onClose();
    } catch (err) {
      const msg = toErrorMessage(err, "No se pudo aplicar la actualización masiva.");
      setError(msg);
      onError?.(msg);
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Programar masivamente"
      size="xl"
      footer={
        <>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={mutation.isPending}
          >
            Cancelar
          </Button>
          <Button
            variant="primary"
            onClick={handleApply}
            disabled={!canSubmit}
            isLoading={mutation.isPending}
          >
            Aplicar a {selectedIds.size} empresa(s)
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        {/* Sección 1: selector de empresas */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-900">
              1. Empresas
            </h3>
            <span className="text-xs text-slate-500">
              {selectedIds.size} seleccionada(s)
            </span>
          </div>

          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Buscar por empresa..."
          />

          <div className="flex flex-wrap gap-2">
            {(
              [
                { id: "todas", label: "Todas" },
                { id: "playwright_enabled", label: "Solo con Playwright" },
                { id: "scheduler_inactivo", label: "Solo pausadas" },
              ] as { id: QuickFilter; label: string }[]
            ).map((f) => {
              const active = quickFilter === f.id;
              return (
                <button
                  type="button"
                  key={f.id}
                  onClick={() => setQuickFilter(f.id)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
                    active
                      ? "bg-slate-900 text-white border-slate-900"
                      : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>

          <div className="border border-slate-200 rounded-md max-h-64 overflow-y-auto">
            <div className="sticky top-0 bg-slate-50 border-b border-slate-200 px-3 py-2 flex items-center gap-2">
              <input
                type="checkbox"
                checked={allVisibleSelected}
                onChange={toggleSelectAllVisible}
                disabled={filteredClients.length === 0}
                className="h-4 w-4 rounded border-slate-300 text-green-600 focus:ring-green-500"
              />
              <span className="text-xs font-medium text-slate-700">
                Seleccionar todos los visibles ({filteredClients.length})
              </span>
            </div>
            {filteredClients.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-slate-400">
                No hay empresas que coincidan con los filtros.
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {filteredClients.map((c) => {
                  const checked = selectedIds.has(c.id);
                  return (
                    <li
                      key={c.id}
                      className="flex items-center gap-3 px-3 py-2 hover:bg-slate-50"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelect(c.id)}
                        className="h-4 w-4 rounded border-slate-300 text-green-600 focus:ring-green-500"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-900 truncate">
                          {c.empresa || "(Sin nombre)"}
                        </div>
                        <code className="text-xs text-slate-500">
                          {c.cuitRepresentado || c.cuit}
                        </code>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <Badge variant={c.schedulerActivo ? "success" : "default"}>
                          {c.schedulerActivo ? "activo" : "pausado"}
                        </Badge>
                        <span className="text-[10px] text-slate-500 tabular-nums">
                          {c.schedulerHoraLocal ?? "—"} ·{" "}
                          {c.schedulerDiasSemana.length}d
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </section>

        {/* Sección 2: config compartida */}
        <section className="space-y-4">
          <h3 className="text-sm font-semibold text-slate-900">
            2. Configuración a aplicar
          </h3>
          <p className="text-xs text-slate-500">
            Tildá los campos que querés cambiar. Los que no marques quedarán intactos
            en cada empresa.
          </p>

          {/* Activo */}
          <div className="rounded-md border border-slate-200 p-3">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={applyActivo}
                onChange={(e) => setApplyActivo(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-green-600 focus:ring-green-500"
              />
              <span className="text-sm font-medium text-slate-700">
                Cambiar estado activo
              </span>
            </label>
            {applyActivo ? (
              <div className="mt-2 ml-6 flex gap-2">
                <button
                  type="button"
                  onClick={() => setActivo(true)}
                  className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                    activo
                      ? "bg-emerald-600 text-white border-emerald-600"
                      : "bg-white text-slate-700 border-slate-300"
                  }`}
                >
                  Activar
                </button>
                <button
                  type="button"
                  onClick={() => setActivo(false)}
                  className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                    !activo
                      ? "bg-slate-700 text-white border-slate-700"
                      : "bg-white text-slate-700 border-slate-300"
                  }`}
                >
                  Pausar
                </button>
              </div>
            ) : null}
          </div>

          {/* Días semana */}
          <div className="rounded-md border border-slate-200 p-3">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={applyDias}
                onChange={(e) => setApplyDias(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-green-600 focus:ring-green-500"
              />
              <span className="text-sm font-medium text-slate-700">
                Cambiar días de la semana
              </span>
            </label>
            {applyDias ? (
              <div className="mt-2 ml-6 flex flex-wrap gap-2">
                {DIAS_SEMANA.map((d) => {
                  const selected = diasSemana.includes(d.value);
                  return (
                    <button
                      type="button"
                      key={d.value}
                      onClick={() => toggleDia(d.value)}
                      className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                        selected
                          ? "bg-green-600 text-white border-green-600"
                          : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      {d.label}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>

          {/* Hora local */}
          <div className="rounded-md border border-slate-200 p-3">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={applyHora}
                onChange={(e) => setApplyHora(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-green-600 focus:ring-green-500"
              />
              <span className="text-sm font-medium text-slate-700">
                Cambiar hora local (HH:MM)
              </span>
            </label>
            {applyHora ? (
              <div className="mt-2 ml-6">
                <input
                  type="time"
                  className="block w-40 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                  value={horaLocal}
                  onChange={(e) => setHoraLocal(e.target.value)}
                />
                {horaInvalida ? (
                  <p className="text-xs text-red-600 mt-1">
                    Hora inválida. Formato esperado HH:MM (24h).
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>

          {/* Días extracción */}
          <div className="rounded-md border border-slate-200 p-3">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={applyDiasExtraccion}
                onChange={(e) => setApplyDiasExtraccion(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-green-600 focus:ring-green-500"
              />
              <span className="text-sm font-medium text-slate-700">
                Cambiar días a extraer
              </span>
            </label>
            {applyDiasExtraccion ? (
              <div className="mt-2 ml-6 space-y-2">
                <p className="text-xs text-slate-500">
                  Ventana temporal hacia atrás desde hoy para cada scrape.
                </p>
                <div className="flex flex-wrap gap-2">
                  {DIAS_EXTRACCION_PRESETS.map((preset) => {
                    const active = diasExtraccion === preset;
                    return (
                      <button
                        type="button"
                        key={preset}
                        onClick={() => {
                          setDiasExtraccion(preset);
                          setDiasExtraccionRaw(String(preset));
                        }}
                        className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                          active
                            ? "bg-green-600 text-white border-green-600"
                            : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        {preset} días
                      </button>
                    );
                  })}
                </div>
                <input
                  type="number"
                  min={DIAS_EXTRACCION_MIN}
                  max={DIAS_EXTRACCION_MAX}
                  className="block w-40 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                  value={diasExtraccionRaw}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const parsed = Number.parseInt(raw, 10);
                    setDiasExtraccionRaw(raw);
                    setDiasExtraccion(Number.isNaN(parsed) ? 0 : parsed);
                  }}
                />
                {diasExtraccionInvalido ? (
                  <p className="text-xs text-red-600">
                    Debe estar entre {DIAS_EXTRACCION_MIN} y {DIAS_EXTRACCION_MAX}.
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

        {error ? <Alert variant="error">{error}</Alert> : null}

        {seleccionVacia ? (
          <Alert variant="info">Seleccioná al menos una empresa para continuar.</Alert>
        ) : !algunCampoMarcado ? (
          <Alert variant="info">
            Tildá al menos un campo de configuración para aplicar.
          </Alert>
        ) : null}
      </div>
    </Modal>
  );
}
