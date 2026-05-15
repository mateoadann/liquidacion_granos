import { useMemo, useState } from "react";
import { PageHeader } from "../components/layout";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmModal,
  Modal,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "../components/ui";
import { SchedulerStatusCard } from "../components/dashboard";
import { useClientsQuery } from "../hooks/useClients";
import {
  useRunSchedulerNowMutation,
  useSchedulerStatusQuery,
  useUpdateTaxpayerSchedulerMutation,
} from "../hooks/useScheduler";
import type { Client } from "../clients";
import { formatDateTime } from "../dateUtils";

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

interface EditFormState {
  diasSemana: string[];
  horaLocal: string;
  diasExtraccion: number;
  diasExtraccionRaw: string;
}

const DIAS_EXTRACCION_PRESETS: number[] = [10, 30, 60];
const DIAS_EXTRACCION_MIN = 1;
const DIAS_EXTRACCION_MAX = 366;

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string" && err.trim()) return err;
  return fallback;
}

interface ToastState {
  variant: "success" | "error" | "info";
  message: string;
}

export function SchedulerPage() {
  const clientsQuery = useClientsQuery();
  const statusQuery = useSchedulerStatusQuery();
  const updateMutation = useUpdateTaxpayerSchedulerMutation();
  const runNowMutation = useRunSchedulerNowMutation();

  const [editing, setEditing] = useState<Client | null>(null);
  const [editForm, setEditForm] = useState<EditFormState>({
    diasSemana: [],
    horaLocal: "06:00",
    diasExtraccion: 90,
    diasExtraccionRaw: "90",
  });
  const [editError, setEditError] = useState<string | null>(null);

  const [bulkConfirmOpen, setBulkConfirmOpen] = useState(false);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  const [pendingToggleId, setPendingToggleId] = useState<number | null>(null);
  const [pendingRunNowId, setPendingRunNowId] = useState<number | null>(null);

  const clients = clientsQuery.data ?? [];

  const bulkCandidates = useMemo(
    () =>
      clients.filter(
        (c) => c.activo && c.playwrightEnabled && !c.schedulerActivo,
      ),
    [clients],
  );

  function showToast(next: ToastState) {
    setToast(next);
    window.setTimeout(() => setToast(null), 5000);
  }

  function openEdit(client: Client) {
    setEditError(null);
    const dias = client.schedulerDiasExtraccion ?? 90;
    setEditForm({
      diasSemana: [...client.schedulerDiasSemana],
      horaLocal: client.schedulerHoraLocal ?? "06:00",
      diasExtraccion: dias,
      diasExtraccionRaw: String(dias),
    });
    setEditing(client);
  }

  function closeEdit() {
    setEditing(null);
    setEditError(null);
  }

  function toggleEditDia(value: string) {
    setEditForm((prev) =>
      prev.diasSemana.includes(value)
        ? { ...prev, diasSemana: prev.diasSemana.filter((d) => d !== value) }
        : { ...prev, diasSemana: [...prev.diasSemana, value] },
    );
  }

  async function handleSaveEdit() {
    if (!editing) return;
    setEditError(null);
    if (!HORA_LOCAL_REGEX.test(editForm.horaLocal)) {
      setEditError("Hora inválida. Formato esperado HH:MM (24h).");
      return;
    }
    if (editForm.diasSemana.length === 0) {
      setEditError("Seleccioná al menos un día.");
      return;
    }
    if (
      !Number.isInteger(editForm.diasExtraccion) ||
      editForm.diasExtraccion < DIAS_EXTRACCION_MIN ||
      editForm.diasExtraccion > DIAS_EXTRACCION_MAX
    ) {
      setEditError(
        `Días a extraer debe estar entre ${DIAS_EXTRACCION_MIN} y ${DIAS_EXTRACCION_MAX}.`,
      );
      return;
    }
    try {
      const orderedDias = DIAS_SEMANA.filter((d) =>
        editForm.diasSemana.includes(d.value),
      ).map((d) => d.value);
      await updateMutation.mutateAsync({
        taxpayerId: editing.id,
        body: {
          dias_semana: orderedDias,
          hora_local: editForm.horaLocal,
          dias_extraccion: editForm.diasExtraccion,
        },
      });
      showToast({
        variant: "success",
        message: `Configuración actualizada para ${editing.empresa}.`,
      });
      closeEdit();
    } catch (err) {
      setEditError(toErrorMessage(err, "No se pudo guardar la configuración."));
    }
  }

  async function handleToggleActivo(client: Client) {
    setPendingToggleId(client.id);
    try {
      await updateMutation.mutateAsync({
        taxpayerId: client.id,
        body: { activo: !client.schedulerActivo },
      });
      showToast({
        variant: "success",
        message: !client.schedulerActivo
          ? `Scheduler activado para ${client.empresa}.`
          : `Scheduler desactivado para ${client.empresa}.`,
      });
    } catch (err) {
      showToast({
        variant: "error",
        message: toErrorMessage(err, "No se pudo actualizar el scheduler."),
      });
    } finally {
      setPendingToggleId(null);
    }
  }

  async function handleRunNow(client: Client) {
    setPendingRunNowId(client.id);
    try {
      const result = await runNowMutation.mutateAsync(client.id);
      showToast({
        variant: "success",
        message: `Job ${result.extraction_job_id} encolado para ${client.empresa}.`,
      });
    } catch (err) {
      showToast({
        variant: "error",
        message: toErrorMessage(err, "No se pudo disparar la extracción."),
      });
    } finally {
      setPendingRunNowId(null);
    }
  }

  async function handleBulkActivate() {
    setBulkConfirmOpen(false);
    if (bulkCandidates.length === 0) {
      showToast({
        variant: "info",
        message: "No hay empresas elegibles para activar en bloque.",
      });
      return;
    }
    setBulkRunning(true);
    let ok = 0;
    let fail = 0;
    for (const candidate of bulkCandidates) {
      try {
        await updateMutation.mutateAsync({
          taxpayerId: candidate.id,
          body: { activo: true },
        });
        ok += 1;
      } catch {
        fail += 1;
      }
    }
    setBulkRunning(false);
    showToast({
      variant: fail === 0 ? "success" : "error",
      message:
        fail === 0
          ? `Scheduler activado en ${ok} empresa(s).`
          : `Activación parcial: ${ok} OK, ${fail} con error.`,
    });
  }

  const diasExtraccionInvalido =
    !Number.isInteger(editForm.diasExtraccion) ||
    editForm.diasExtraccion < DIAS_EXTRACCION_MIN ||
    editForm.diasExtraccion > DIAS_EXTRACCION_MAX;

  const isLoading = clientsQuery.isLoading;
  const clientsError = clientsQuery.error
    ? toErrorMessage(clientsQuery.error, "Error al cargar empresas.")
    : null;
  const statusError = statusQuery.error
    ? toErrorMessage(statusQuery.error, "Error al cargar el estado del scheduler.")
    : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scheduler de extracción automática"
        subtitle="Gestioná los disparos programados de Arca por empresa."
        actions={
          <Button
            variant="primary"
            onClick={() => setBulkConfirmOpen(true)}
            disabled={bulkRunning || bulkCandidates.length === 0}
            isLoading={bulkRunning}
          >
            Activar en bloque ({bulkCandidates.length})
          </Button>
        }
      />

      <SchedulerStatusCard
        status={statusQuery.data}
        isLoading={statusQuery.isLoading}
        errorMessage={statusError}
      />

      {toast ? <Alert variant={toast.variant}>{toast.message}</Alert> : null}

      <Card padding="none">
        <div className="border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Empresas</h2>
          <p className="text-sm text-slate-500">
            Configurá el scheduler de cada empresa o ejecutá una extracción manual.
          </p>
        </div>

        {isLoading ? (
          <div className="flex justify-center items-center py-10">
            <Spinner size="lg" />
          </div>
        ) : clientsError ? (
          <div className="px-6 py-4">
            <Alert variant="error">{clientsError}</Alert>
          </div>
        ) : clients.length === 0 ? (
          <div className="px-6 py-10 text-center text-sm text-slate-500">
            No hay empresas registradas.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableCell header>Empresa</TableCell>
                <TableCell header>CUIT</TableCell>
                <TableCell header>Scheduler</TableCell>
                <TableCell header>Días</TableCell>
                <TableCell header>Hora</TableCell>
                <TableCell header>
                  <span title="Ventana temporal hacia atrás desde hoy para cada scrape">
                    Días extracción
                  </span>
                </TableCell>
                <TableCell header>Último OK</TableCell>
                <TableCell header>Último error</TableCell>
                <TableCell header className="text-right">
                  Acciones
                </TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.map((client) => {
                const togglePending =
                  pendingToggleId === client.id && updateMutation.isPending;
                const runPending =
                  pendingRunNowId === client.id && runNowMutation.isPending;
                const canRunNow = client.activo && client.schedulerActivo;
                const errorMessage = client.schedulerUltimoError;

                return (
                  <TableRow key={client.id}>
                    <TableCell>
                      <div className="font-medium text-slate-900">
                        {client.empresa || "(Sin nombre)"}
                      </div>
                      {!client.activo ? (
                        <Badge variant="warning" className="mt-1">
                          Inactivo
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <code className="text-xs">{client.cuitRepresentado || client.cuit}</code>
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        onClick={() => handleToggleActivo(client)}
                        disabled={togglePending || !client.activo}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                          client.schedulerActivo
                            ? "bg-emerald-500"
                            : "bg-slate-300"
                        }`}
                        aria-label={
                          client.schedulerActivo
                            ? "Desactivar scheduler"
                            : "Activar scheduler"
                        }
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            client.schedulerActivo
                              ? "translate-x-6"
                              : "translate-x-1"
                          }`}
                        />
                      </button>
                    </TableCell>
                    <TableCell>
                      {client.schedulerDiasSemana.length === 0 ? (
                        <span className="text-xs text-slate-400">—</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {client.schedulerDiasSemana.map((d) => (
                            <Badge key={d} variant="info">
                              {d}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="text-sm tabular-nums">
                        {client.schedulerHoraLocal ?? "—"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span
                        className="text-sm tabular-nums text-slate-700"
                        title="Ventana temporal hacia atrás desde hoy para cada scrape"
                      >
                        {client.schedulerDiasExtraccion} d
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-slate-600">
                        {formatDateTime(client.schedulerUltimoOk)}
                      </span>
                    </TableCell>
                    <TableCell>
                      {errorMessage ? (
                        <span
                          title={errorMessage}
                          className="inline-flex max-w-[14rem] truncate"
                        >
                          <Badge variant="error">{errorMessage}</Badge>
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => openEdit(client)}
                          disabled={togglePending}
                        >
                          Editar
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => handleRunNow(client)}
                          disabled={!canRunNow || runPending}
                          isLoading={runPending}
                          title={
                            canRunNow
                              ? "Disparar extracción ahora"
                              : "El scheduler debe estar activo y la empresa habilitada"
                          }
                        >
                          Scrapear ahora
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      <Modal
        isOpen={editing !== null}
        onClose={closeEdit}
        title={
          editing
            ? `Configurar scheduler — ${editing.empresa}`
            : "Configurar scheduler"
        }
        size="lg"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={closeEdit}
              disabled={updateMutation.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={handleSaveEdit}
              isLoading={updateMutation.isPending}
              disabled={diasExtraccionInvalido}
            >
              Guardar
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Días de la semana
            </label>
            <div className="flex flex-wrap gap-2">
              {DIAS_SEMANA.map((d) => {
                const selected = editForm.diasSemana.includes(d.value);
                return (
                  <button
                    type="button"
                    key={d.value}
                    onClick={() => toggleEditDia(d.value)}
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
          </div>

          <div>
            <label
              className="block text-sm font-medium text-slate-700 mb-1"
              htmlFor="scheduler-hora"
            >
              Hora local (HH:MM)
            </label>
            <input
              id="scheduler-hora"
              type="time"
              className="block w-40 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              value={editForm.horaLocal}
              onChange={(e) =>
                setEditForm((prev) => ({ ...prev, horaLocal: e.target.value }))
              }
            />
            <p className="text-xs text-slate-500 mt-1">
              Formato 24h. Hora de Argentina/Córdoba.
            </p>
          </div>

          <div>
            <label
              className="block text-sm font-medium text-slate-700 mb-1"
              htmlFor="scheduler-dias-extraccion"
            >
              Días a extraer
            </label>
            <p className="text-xs text-slate-500 mb-2">
              Ventana temporal hacia atrás desde hoy para cada scrape.
            </p>
            <div className="flex flex-wrap gap-2 mb-2">
              {DIAS_EXTRACCION_PRESETS.map((preset) => {
                const active = editForm.diasExtraccion === preset;
                return (
                  <button
                    type="button"
                    key={preset}
                    onClick={() =>
                      setEditForm((prev) => ({
                        ...prev,
                        diasExtraccion: preset,
                        diasExtraccionRaw: String(preset),
                      }))
                    }
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
              id="scheduler-dias-extraccion"
              type="number"
              min={DIAS_EXTRACCION_MIN}
              max={DIAS_EXTRACCION_MAX}
              className="block w-40 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              value={editForm.diasExtraccionRaw}
              onChange={(e) => {
                const raw = e.target.value;
                const parsed = Number.parseInt(raw, 10);
                setEditForm((prev) => ({
                  ...prev,
                  diasExtraccionRaw: raw,
                  diasExtraccion: Number.isNaN(parsed) ? 0 : parsed,
                }));
              }}
            />
            {!Number.isInteger(editForm.diasExtraccion) ||
            editForm.diasExtraccion < DIAS_EXTRACCION_MIN ||
            editForm.diasExtraccion > DIAS_EXTRACCION_MAX ? (
              <p className="text-xs text-red-600 mt-1">
                Debe estar entre {DIAS_EXTRACCION_MIN} y {DIAS_EXTRACCION_MAX}.
              </p>
            ) : null}
          </div>

          {editError ? <Alert variant="error">{editError}</Alert> : null}
        </div>
      </Modal>

      <ConfirmModal
        isOpen={bulkConfirmOpen}
        onClose={() => setBulkConfirmOpen(false)}
        onConfirm={handleBulkActivate}
        title="Activar scheduler en bloque"
        message={`Se activará el scheduler en ${bulkCandidates.length} empresa(s) elegibles (con Playwright habilitado y empresa activa). ¿Continuar?`}
        confirmLabel="Activar"
        cancelLabel="Cancelar"
        variant="primary"
        isLoading={bulkRunning}
      />
    </div>
  );
}
