import { useMemo, useState } from "react";
import { PageHeader } from "../components/layout";
import {
  Alert,
  Badge,
  Button,
  Card,
  Modal,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "../components/ui";
import {
  BulkSchedulerModal,
  SchedulerStatusCard,
} from "../components/dashboard";
import { useClientsQuery } from "../hooks/useClients";
import {
  useBulkUpdateSchedulerMutation,
  useLastErrorDetailQuery,
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

function hasStatus(err: unknown): err is { status: number; message: string } {
  return (
    typeof err === "object" &&
    err !== null &&
    "status" in err &&
    typeof (err as { status: unknown }).status === "number"
  );
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
  const bulkMutation = useBulkUpdateSchedulerMutation();

  const [editing, setEditing] = useState<Client | null>(null);
  const [editForm, setEditForm] = useState<EditFormState>({
    diasSemana: [],
    horaLocal: "06:00",
    diasExtraccion: 90,
    diasExtraccionRaw: "90",
  });
  const [editError, setEditError] = useState<string | null>(null);

  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  const [pendingToggleId, setPendingToggleId] = useState<number | null>(null);
  const [pendingRunNowId, setPendingRunNowId] = useState<number | null>(null);
  const [errorDetailTaxpayerId, setErrorDetailTaxpayerId] = useState<
    number | null
  >(null);

  const clients = clientsQuery.data ?? [];

  const eligibleBulkClients = useMemo(
    () => clients.filter((c) => c.activo && c.playwrightEnabled),
    [clients],
  );

  const errorDetailQuery = useLastErrorDetailQuery(
    errorDetailTaxpayerId,
    errorDetailTaxpayerId !== null,
  );

  const errorDetailClient = useMemo(
    () =>
      errorDetailTaxpayerId !== null
        ? clients.find((c) => c.id === errorDetailTaxpayerId) ?? null
        : null,
    [clients, errorDetailTaxpayerId],
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
      setEditError("La hora debe tener formato HH:MM.");
      return;
    }
    if (editForm.diasSemana.length === 0) {
      setEditError("Elegí al menos un día.");
      return;
    }
    if (
      !Number.isInteger(editForm.diasExtraccion) ||
      editForm.diasExtraccion < DIAS_EXTRACCION_MIN ||
      editForm.diasExtraccion > DIAS_EXTRACCION_MAX
    ) {
      setEditError(
        `El período debe estar entre ${DIAS_EXTRACCION_MIN} y ${DIAS_EXTRACCION_MAX} días.`,
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
        message: `Programación actualizada para ${editing.empresa}.`,
      });
      closeEdit();
    } catch (err) {
      setEditError(toErrorMessage(err, "No se pudo guardar la programación."));
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
          ? `${client.empresa} quedó programada.`
          : `${client.empresa} quedó pausada.`,
      });
    } catch (err) {
      showToast({
        variant: "error",
        message: toErrorMessage(err, "No se pudo actualizar la programación."),
      });
    } finally {
      setPendingToggleId(null);
    }
  }

  async function handleRunNow(client: Client) {
    setPendingRunNowId(client.id);
    try {
      await runNowMutation.mutateAsync(client.id);
      showToast({
        variant: "success",
        message: "Consulta iniciada.",
      });
    } catch (err) {
      showToast({
        variant: "error",
        message: toErrorMessage(
          err,
          "No se pudo iniciar la consulta. Reintentá más tarde.",
        ),
      });
    } finally {
      setPendingRunNowId(null);
    }
  }

  async function handleBulkSubmit(body: {
    taxpayer_ids: number[];
    activo: boolean;
    dias_semana: string[];
    hora_local: string;
    dias_extraccion: number;
  }) {
    setBulkError(null);
    try {
      const result = await bulkMutation.mutateAsync(body);
      setBulkModalOpen(false);
      showToast({
        variant: "success",
        message: `${result.total} ${
          result.total === 1 ? "empresa programada" : "empresas programadas"
        }.`,
      });
    } catch (err) {
      if (hasStatus(err) && err.status === 404) {
        setBulkError("Algunas empresas no se encontraron. Reintentá.");
      } else {
        setBulkError(
          toErrorMessage(err, "No se pudieron programar las empresas."),
        );
      }
    }
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
    ? toErrorMessage(
        statusQuery.error,
        "Error al cargar el estado de la programación.",
      )
    : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Programación de consultas"
        subtitle="Programar consultas automáticas a Arca por empresa"
        actions={
          <Button
            variant="primary"
            onClick={() => {
              setBulkError(null);
              setBulkModalOpen(true);
            }}
            disabled={eligibleBulkClients.length === 0}
          >
            Programar empresas
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
            Configurá la programación de cada empresa o consultá Arca
            manualmente.
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
                <TableCell header>Estado</TableCell>
                <TableCell header>Días</TableCell>
                <TableCell header>Hora</TableCell>
                <TableCell header>Última consulta exitosa</TableCell>
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
                          Inactiva
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <code className="text-xs">
                        {client.cuitRepresentado || client.cuit}
                      </code>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
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
                              ? "Pausar programación"
                              : "Activar programación"
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
                        <Badge
                          variant={client.schedulerActivo ? "success" : "default"}
                          size="sm"
                        >
                          {client.schedulerActivo ? "Activa" : "Pausada"}
                        </Badge>
                      </div>
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
                      <span className="text-xs text-slate-600">
                        {formatDateTime(client.schedulerUltimoOk)}
                      </span>
                    </TableCell>
                    <TableCell>
                      {errorMessage ? (
                        <div className="max-w-[16rem]">
                          <Badge variant="error" className="whitespace-normal">
                            {errorMessage}
                          </Badge>
                          <button
                            type="button"
                            onClick={() =>
                              setErrorDetailTaxpayerId(client.id)
                            }
                            className="block text-xs text-blue-600 underline mt-1 hover:text-blue-800"
                          >
                            Ver detalle técnico
                          </button>
                        </div>
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
                              ? "Consultar Arca ahora"
                              : "Activá la programación de la empresa para consultar manualmente."
                          }
                        >
                          Consultar ahora
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
            ? `Configurar programación — ${editing.empresa}`
            : "Configurar programación"
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
              Hora (HH:MM)
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
              Período a consultar
            </label>
            <p className="text-xs text-slate-500 mb-2">
              Cuántos días hacia atrás desde hoy se consultan en cada corrida.
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
                El período debe estar entre {DIAS_EXTRACCION_MIN} y{" "}
                {DIAS_EXTRACCION_MAX}.
              </p>
            ) : null}
          </div>

          {editError ? <Alert variant="error">{editError}</Alert> : null}
        </div>
      </Modal>

      <BulkSchedulerModal
        isOpen={bulkModalOpen}
        clients={eligibleBulkClients}
        isSubmitting={bulkMutation.isPending}
        errorMessage={bulkError}
        onClose={() => setBulkModalOpen(false)}
        onSubmit={handleBulkSubmit}
      />

      <Modal
        isOpen={errorDetailTaxpayerId !== null}
        onClose={() => setErrorDetailTaxpayerId(null)}
        title={
          errorDetailClient
            ? `Detalle técnico — ${errorDetailClient.empresa}`
            : "Detalle técnico"
        }
        size="md"
        footer={
          <Button
            variant="secondary"
            onClick={() => setErrorDetailTaxpayerId(null)}
          >
            Cerrar
          </Button>
        }
      >
        {errorDetailQuery.isLoading ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : errorDetailQuery.error ? (
          <Alert variant="error">
            {toErrorMessage(
              errorDetailQuery.error,
              "No se pudo cargar el detalle técnico.",
            )}
          </Alert>
        ) : errorDetailQuery.data ? (
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-xs font-medium text-slate-500">Fase</p>
              <p className="text-slate-800 font-mono">
                {errorDetailQuery.data.failure_phase ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">
                Mensaje técnico
              </p>
              <pre className="text-xs text-slate-800 bg-slate-50 border border-slate-200 rounded p-2 whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                {errorDetailQuery.data.failure_message_technical ??
                  "No hay detalle técnico disponible."}
              </pre>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Finalizado</p>
              <p className="text-slate-800 text-xs">
                {errorDetailQuery.data.finished_at
                  ? formatDateTime(errorDetailQuery.data.finished_at)
                  : "—"}
              </p>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
