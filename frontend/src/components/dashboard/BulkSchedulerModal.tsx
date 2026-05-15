import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Modal } from "../ui";
import type { Client } from "../../clients";

interface DiaChip {
  value: string;
  label: string;
}

const DIAS_SEMANA: DiaChip[] = [
  { value: "lun", label: "L" },
  { value: "mar", label: "M" },
  { value: "mie", label: "X" },
  { value: "jue", label: "J" },
  { value: "vie", label: "V" },
  { value: "sab", label: "S" },
  { value: "dom", label: "D" },
];

const HORA_LOCAL_REGEX = /^([01]\d|2[0-3]):[0-5]\d$/;
const DIAS_EXTRACCION_PRESETS: number[] = [10, 30, 60];
const DIAS_EXTRACCION_MIN = 1;
const DIAS_EXTRACCION_MAX = 366;

interface BulkSchedulerBody {
  taxpayer_ids: number[];
  activo: boolean;
  dias_semana: string[];
  hora_local: string;
  dias_extraccion: number;
}

interface BulkSchedulerModalProps {
  isOpen: boolean;
  clients: Client[];
  isSubmitting: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onSubmit: (body: BulkSchedulerBody) => Promise<void> | void;
}

type PeriodoPreset = 10 | 30 | 60 | "otros";

export function BulkSchedulerModal({
  isOpen,
  clients,
  isSubmitting,
  errorMessage,
  onClose,
  onSubmit,
}: BulkSchedulerModalProps) {
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [diasSemana, setDiasSemana] = useState<string[]>([
    "lun",
    "mar",
    "mie",
    "jue",
    "vie",
  ]);
  const [horaLocal, setHoraLocal] = useState("06:00");
  const [periodoPreset, setPeriodoPreset] = useState<PeriodoPreset>(30);
  const [periodoCustomRaw, setPeriodoCustomRaw] = useState("90");

  useEffect(() => {
    if (!isOpen) return;
    setSearch("");
    setSelectedIds([]);
    setDiasSemana(["lun", "mar", "mie", "jue", "vie"]);
    setHoraLocal("06:00");
    setPeriodoPreset(30);
    setPeriodoCustomRaw("90");
  }, [isOpen]);

  const filteredClients = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return clients;
    return clients.filter((c) => {
      const empresa = (c.empresa ?? "").toLowerCase();
      const cuit = (c.cuit ?? "").toLowerCase();
      return empresa.includes(term) || cuit.includes(term);
    });
  }, [clients, search]);

  const allFilteredSelected =
    filteredClients.length > 0 &&
    filteredClients.every((c) => selectedIds.includes(c.id));

  function toggleClient(id: number) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function toggleSelectAll() {
    if (allFilteredSelected) {
      const filteredIds = new Set(filteredClients.map((c) => c.id));
      setSelectedIds((prev) => prev.filter((id) => !filteredIds.has(id)));
    } else {
      const merged = new Set(selectedIds);
      for (const c of filteredClients) merged.add(c.id);
      setSelectedIds(Array.from(merged));
    }
  }

  function toggleDia(value: string) {
    setDiasSemana((prev) =>
      prev.includes(value) ? prev.filter((d) => d !== value) : [...prev, value],
    );
  }

  const diasExtraccion: number | null = useMemo(() => {
    if (periodoPreset === "otros") {
      const parsed = Number.parseInt(periodoCustomRaw, 10);
      if (
        Number.isNaN(parsed) ||
        parsed < DIAS_EXTRACCION_MIN ||
        parsed > DIAS_EXTRACCION_MAX
      ) {
        return null;
      }
      return parsed;
    }
    return periodoPreset;
  }, [periodoPreset, periodoCustomRaw]);

  const horaValida = HORA_LOCAL_REGEX.test(horaLocal);
  const diasValidos = diasSemana.length > 0;
  const periodoValido = diasExtraccion !== null;
  const empresasValidas = selectedIds.length > 0;
  const canSubmit =
    empresasValidas &&
    diasValidos &&
    horaValida &&
    periodoValido &&
    !isSubmitting;

  async function handleSubmit() {
    if (!canSubmit || diasExtraccion === null) return;
    // Orden canónico de días para evitar reordering inesperado.
    const orderedDias = DIAS_SEMANA.filter((d) =>
      diasSemana.includes(d.value),
    ).map((d) => d.value);
    await onSubmit({
      taxpayer_ids: selectedIds,
      activo: true,
      dias_semana: orderedDias,
      hora_local: horaLocal,
      dias_extraccion: diasExtraccion,
    });
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={isSubmitting ? () => undefined : onClose}
      title="Programar empresas"
      size="lg"
      footer={
        <>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button
            variant="primary"
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            isLoading={isSubmitting}
          >
            {`Programar ${selectedIds.length} ${
              selectedIds.length === 1 ? "empresa" : "empresas"
            }`}
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        {/* Sección 1: Empresas */}
        <section>
          <h3 className="text-sm font-semibold text-slate-900 mb-2">
            1. Empresas ({selectedIds.length} seleccionadas)
          </h3>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por empresa o CUIT..."
            className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 mb-2"
          />
          <div className="rounded-md border border-slate-200">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2">
              <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={allFilteredSelected}
                  onChange={toggleSelectAll}
                  disabled={filteredClients.length === 0}
                />
                Seleccionar todos
              </label>
              <span className="text-xs text-slate-500">
                {filteredClients.length} disponibles
              </span>
            </div>
            <div className="max-h-56 overflow-y-auto">
              {filteredClients.length === 0 ? (
                <p className="px-3 py-4 text-sm text-slate-500">
                  No hay empresas que coincidan con la búsqueda.
                </p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {filteredClients.map((c) => {
                    const checked = selectedIds.includes(c.id);
                    return (
                      <li key={c.id}>
                        <label className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleClient(c.id)}
                          />
                          <span className="flex-1">
                            <span className="font-medium text-slate-800">
                              {c.empresa || "(Sin nombre)"}
                            </span>
                            <span className="ml-2 text-xs text-slate-500">
                              {c.cuit}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </section>

        {/* Sección 2: Cuándo */}
        <section>
          <h3 className="text-sm font-semibold text-slate-900 mb-2">
            2. Cuándo
          </h3>
          <div className="space-y-3">
            <div>
              <p className="text-xs font-medium text-slate-700 mb-1">Días</p>
              <div className="flex flex-wrap gap-2">
                {DIAS_SEMANA.map((d) => {
                  const selected = diasSemana.includes(d.value);
                  return (
                    <button
                      type="button"
                      key={d.value}
                      onClick={() => toggleDia(d.value)}
                      className={`h-9 w-9 rounded-md border text-sm font-medium transition-colors ${
                        selected
                          ? "bg-green-600 text-white border-green-600"
                          : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                      }`}
                      aria-pressed={selected}
                      aria-label={d.value}
                    >
                      {d.label}
                    </button>
                  );
                })}
              </div>
              {!diasValidos ? (
                <p className="text-xs text-red-600 mt-1">
                  Elegí al menos un día.
                </p>
              ) : null}
            </div>
            <div>
              <label
                htmlFor="bulk-hora"
                className="block text-xs font-medium text-slate-700 mb-1"
              >
                Hora
              </label>
              <input
                id="bulk-hora"
                type="time"
                value={horaLocal}
                onChange={(e) => setHoraLocal(e.target.value)}
                className="block w-32 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              />
              {!horaValida ? (
                <p className="text-xs text-red-600 mt-1">
                  La hora debe tener formato HH:MM.
                </p>
              ) : null}
            </div>
          </div>
        </section>

        {/* Sección 3: Período a consultar */}
        <section>
          <h3 className="text-sm font-semibold text-slate-900 mb-2">
            3. Período a consultar
          </h3>
          <div className="space-y-2">
            {DIAS_EXTRACCION_PRESETS.map((preset) => (
              <label
                key={preset}
                className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer"
              >
                <input
                  type="radio"
                  name="bulk-periodo"
                  checked={periodoPreset === preset}
                  onChange={() => setPeriodoPreset(preset as PeriodoPreset)}
                />
                {preset} días
              </label>
            ))}
            <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input
                type="radio"
                name="bulk-periodo"
                checked={periodoPreset === "otros"}
                onChange={() => setPeriodoPreset("otros")}
              />
              Otros:
              <input
                type="number"
                min={DIAS_EXTRACCION_MIN}
                max={DIAS_EXTRACCION_MAX}
                value={periodoCustomRaw}
                onChange={(e) => {
                  setPeriodoCustomRaw(e.target.value);
                  setPeriodoPreset("otros");
                }}
                disabled={periodoPreset !== "otros"}
                className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 disabled:bg-slate-100 disabled:text-slate-400"
              />
              días
            </label>
            {!periodoValido ? (
              <p className="text-xs text-red-600 mt-1">
                El período debe estar entre {DIAS_EXTRACCION_MIN} y{" "}
                {DIAS_EXTRACCION_MAX} días.
              </p>
            ) : null}
          </div>
        </section>

        {errorMessage ? <Alert variant="error">{errorMessage}</Alert> : null}
      </div>
    </Modal>
  );
}
