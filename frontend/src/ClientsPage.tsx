import { useEffect, useMemo, useState } from "react";
import CertificateUpload from "./CertificateUpload";
import ClientForm, { type ClientFormMode, type ClientFormValues } from "./ClientForm";
import ClientTable from "./ClientTable";
import ConfigValidationPanel from "./ConfigValidationPanel";
import RunPlaywrightModal from "./RunPlaywrightModal";
import type { Client, ClientValidationResult, PlaywrightPipelineRunResult } from "./clients";
import {
  useClientsQuery,
  useCreateClientMutation,
  usePlaywrightJobQuery,
  useDeleteClientMutation,
  useRunPlaywrightPipelineMutation,
  useUpdateClientMutation,
  useUploadCertificatesMutation,
  useValidateConfigMutation,
} from "./useClients";

type PageView = "list" | "form" | "certificates" | "validation";

interface UiMessage {
  type: "success" | "error";
  text: string;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Ocurrió un error inesperado";
}

export default function ClientsPage() {
  const [view, setView] = useState<PageView>("list");
  const [formMode, setFormMode] = useState<ClientFormMode>("create");
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [validationResult, setValidationResult] = useState<ClientValidationResult | null>(
    null
  );
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState<UiMessage | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [certificateError, setCertificateError] = useState<string | null>(null);
  const [certificateSuccess, setCertificateSuccess] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [runModalOpen, setRunModalOpen] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<PlaywrightPipelineRunResult | null>(null);
  const [runJobId, setRunJobId] = useState<number | null>(null);
  const [lastNotifiedJobId, setLastNotifiedJobId] = useState<number | null>(null);

  const clientsQuery = useClientsQuery();
  const createClientMutation = useCreateClientMutation();
  const updateClientMutation = useUpdateClientMutation();
  const deleteClientMutation = useDeleteClientMutation();
  const uploadCertificatesMutation = useUploadCertificatesMutation();
  const validateConfigMutation = useValidateConfigMutation();
  const runPlaywrightMutation = useRunPlaywrightPipelineMutation();
  const runJobQuery = usePlaywrightJobQuery(runJobId);

  const clients = clientsQuery.data ?? [];
  const eligiblePlaywrightClients = useMemo(
    () => clients.filter((client) => client.activo && client.playwrightEnabled),
    [clients]
  );

  const filteredClients = useMemo(() => {
    const trimmed = search.trim().toLowerCase();
    if (!trimmed) return clients;

    return clients.filter((client) => {
      const empresa = client.empresa.toLowerCase();
      const cuit = client.cuit.toLowerCase();
      return empresa.includes(trimmed) || cuit.includes(trimmed);
    });
  }, [clients, search]);

  const anyRowActionLoading =
    deleteClientMutation.isPending ||
    uploadCertificatesMutation.isPending ||
    validateConfigMutation.isPending ||
    runPlaywrightMutation.isPending;

  const activeClient = useMemo(() => {
    if (!selectedClient) return null;
    return clients.find((item) => item.id === selectedClient.id) ?? selectedClient;
  }, [clients, selectedClient]);

  function goToList() {
    setView("list");
    setSelectedClient(null);
    setValidationResult(null);
    setFormError(null);
    setCertificateError(null);
    setCertificateSuccess(null);
    setValidationError(null);
  }

  function openCreateForm() {
    setFormMode("create");
    setSelectedClient(null);
    setFormError(null);
    setView("form");
  }

  function openEditForm(client: Client) {
    setFormMode("edit");
    setSelectedClient(client);
    setFormError(null);
    setView("form");
  }

  async function handleSubmitForm(values: ClientFormValues) {
    const payload = {
      empresa: values.empresa.trim(),
      cuit: values.cuit.trim(),
      cuit_representado: values.cuitRepresentado.trim(),
      ambiente: values.ambiente,
      activo: values.activo,
    };

    setFormError(null);

    try {
      if (formMode === "create") {
        await createClientMutation.mutateAsync({
          ...payload,
          clave_fiscal: values.claveFiscal.trim(),
        });
        setMessage({ type: "success", text: "Cliente creado correctamente" });
      } else if (selectedClient) {
        const updatePayload = {
          ...payload,
          ...(values.claveFiscal.trim()
            ? { clave_fiscal: values.claveFiscal.trim() }
            : {}),
        };

        await updateClientMutation.mutateAsync({
          clientId: selectedClient.id,
          input: updatePayload,
        });
        setMessage({ type: "success", text: "Cliente actualizado correctamente" });
      }

      goToList();
    } catch (error) {
      setFormError(getErrorMessage(error));
    }
  }

  async function handleDeactivate(client: Client) {
    const confirmed = window.confirm(
      `Se va a desactivar el cliente ${client.empresa}. ¿Desea continuar?`
    );
    if (!confirmed) return;

    try {
      await deleteClientMutation.mutateAsync(client.id);
      setMessage({ type: "success", text: "Cliente desactivado" });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    }
  }

  function openCertificates(client: Client) {
    setSelectedClient(client);
    setCertificateError(null);
    setCertificateSuccess(null);
    setView("certificates");
  }

  async function handleUploadCertificates(files: { certFile: File; keyFile: File }) {
    if (!activeClient) return;

    setCertificateError(null);
    setCertificateSuccess(null);

    try {
      const response = await uploadCertificatesMutation.mutateAsync({
        clientId: activeClient.id,
        certFile: files.certFile,
        keyFile: files.keyFile,
      });

      setCertificateSuccess(response.message ?? "Certificados válidos y vinculados");
      setMessage({ type: "success", text: "Certificados actualizados" });
    } catch (error) {
      setCertificateError(getErrorMessage(error));
    }
  }

  async function runValidation(client: Client) {
    setValidationError(null);
    setValidationResult(null);

    try {
      const result = await validateConfigMutation.mutateAsync(client.id);
      setValidationResult(result);
    } catch (error) {
      setValidationError(getErrorMessage(error));
    }
  }

  function openValidation(client: Client) {
    setSelectedClient(client);
    setView("validation");
    void runValidation(client);
  }

  function openRunModal() {
    setRunError(null);
    setRunModalOpen(true);
  }

  async function handleRunPlaywright(input: {
    fechaDesde: string;
    fechaHasta: string;
    taxpayerIds?: number[];
  }) {
    setRunError(null);
    try {
      const jobs = await runPlaywrightMutation.mutateAsync(input);
      // Legacy page tracks a single job; pick the first one if any was enqueued.
      setRunJobId(jobs[0]?.id ?? null);
      setRunModalOpen(false);
      setMessage({
        type: "success",
        text:
          jobs.length > 1
            ? `${jobs.length} extracciones encoladas.`
            : "Consulta iniciada.",
      });
    } catch (error) {
      setRunError(getErrorMessage(error));
    }
  }

  useEffect(() => {
    const job = runJobQuery.data;
    if (!job) return;
    if (job.id === lastNotifiedJobId) return;

    if (job.status === "completed") {
      if (job.result) {
        setRunResult(job.result);
        setMessage({
          type: job.result.taxpayersError > 0 ? "error" : "success",
          text:
            job.result.taxpayersError > 0
              ? `Consulta finalizada con errores: ${job.result.taxpayersOk}/${job.result.taxpayersTotal} empresa(s) OK.`
              : `Consulta finalizada: ${job.result.taxpayersOk} empresa(s) OK.`,
        });
      } else {
        setMessage({
          type: "error",
          text: "Hubo un problema con la consulta. Reintentá más tarde.",
        });
      }
      setLastNotifiedJobId(job.id);
      return;
    }

    if (job.status === "partial") {
      if (job.result) {
        setRunResult(job.result);
      }
      setMessage({
        type: "error",
        text: job.result
          ? `Consulta finalizada parcialmente: ${job.result.taxpayersOk}/${job.result.taxpayersTotal} empresa(s) OK. Revisá el detalle por empresa.`
          : "Consulta finalizada parcialmente. Revisá el detalle por empresa.",
      });
      setLastNotifiedJobId(job.id);
      return;
    }

    if (job.status === "failed") {
      if (job.result) {
        setRunResult(job.result);
      }
      setMessage({
        type: "error",
        text: "Hubo un problema con la consulta. Reintentá más tarde.",
      });
      setLastNotifiedJobId(job.id);
    }
  }, [runJobQuery.data, lastNotifiedJobId]);

  return (
    <main className="mx-auto max-w-6xl p-6">
      <header className="mb-4 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Gestión de clientes</h1>
      </header>

      {message ? (
        <div
          className={`mb-4 rounded-md p-3 text-sm ${
            message.type === "success"
              ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border border-red-200 bg-red-50 text-red-700"
          }`}
        >
          {message.text}
        </div>
      ) : null}

      {clientsQuery.isError ? (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {getErrorMessage(clientsQuery.error)}
        </div>
      ) : null}

      {runResult ? (
        <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Última consulta</h2>
          <p className="mt-1 text-sm text-slate-600">
            Rango: {runResult.fechaDesde} → {runResult.fechaHasta} · Empresas:{" "}
            {runResult.taxpayersTotal} · OK: {runResult.taxpayersOk} · Parciales:{" "}
            {runResult.taxpayersPartial} · Error: {runResult.taxpayersError}
          </p>
          <div className="mt-3 space-y-2">
            {runResult.results.map((item) => {
              const itemClass =
                item.outcome === "done"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : item.outcome === "partial"
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-red-200 bg-red-50 text-red-800";
              return (
                <div
                  key={item.taxpayerId}
                  className={`rounded-md border px-3 py-2 text-sm ${itemClass}`}
                >
                  <p className="font-medium">
                    {item.empresa} (id {item.taxpayerId})
                  </p>
                  <p>
                    COEs detectados: {item.totalCoesDetectados} · nuevos: {item.totalCoesNuevos} ·
                    omitidos: {item.totalOmitidosExistentes} · procesados OK:{" "}
                    {item.totalProcesadosOk} · error: {item.totalProcesadosError}
                  </p>
                  {item.error ? <p>Error: {item.error}</p> : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {runJobQuery.data ? (
        <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Consulta en curso</h2>
          <p className="mt-1 text-sm text-slate-600">
            Estado: {runJobQuery.data.status}
          </p>
          {runJobQuery.data.progress ? (
            <>
              <div className="mt-3">
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full bg-blue-600 transition-all"
                    style={{
                      width: `${
                        runJobQuery.data.progress.totalClients > 0
                          ? (runJobQuery.data.progress.completedClients /
                              runJobQuery.data.progress.totalClients) *
                            100
                          : 0
                      }%`,
                    }}
                  />
                </div>
                <p className="mt-1 text-xs text-slate-600">
                  Progreso: {runJobQuery.data.progress.completedClients}/
                  {runJobQuery.data.progress.totalClients} empresas
                </p>
              </div>
              <div className="mt-3 space-y-2">
                {runJobQuery.data.progress.clients.map((clientProgress) => {
                  const statusClass =
                    clientProgress.status === "done"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : clientProgress.status === "partial"
                        ? "border-amber-200 bg-amber-50 text-amber-800"
                        : clientProgress.status === "error"
                          ? "border-red-200 bg-red-50 text-red-800"
                          : clientProgress.status === "running"
                            ? "border-blue-200 bg-blue-50 text-blue-800"
                            : "border-slate-200 bg-slate-50 text-slate-700";

                  const isFinished =
                    clientProgress.status === "done" ||
                    clientProgress.status === "partial" ||
                    clientProgress.status === "error";

                  return (
                    <div
                      key={clientProgress.taxpayerId}
                      className={`rounded-md border px-3 py-2 text-sm ${statusClass}`}
                    >
                      <p className="font-medium">
                        {clientProgress.empresa} (id {clientProgress.taxpayerId}) ·{" "}
                        {clientProgress.status}
                      </p>
                      {isFinished ? (
                        <p>
                          COEs detectados: {clientProgress.totalCoesDetectados} · nuevos:{" "}
                          {clientProgress.totalCoesNuevos} · procesados OK: {clientProgress.totalProcesadosOk} ·
                          error: {clientProgress.totalProcesadosError}
                        </p>
                      ) : null}
                      {clientProgress.error ? <p>Error: {clientProgress.error}</p> : null}
                    </div>
                  );
                })}
              </div>
            </>
          ) : null}
        </section>
      ) : null}

      {view === "list" ? (
        <ClientTable
          clients={filteredClients}
          isLoading={clientsQuery.isLoading}
          search={search}
          onSearchChange={setSearch}
          onNewClient={openCreateForm}
          onRunPlaywright={openRunModal}
          runPlaywrightDisabled={
            clientsQuery.isLoading ||
            runPlaywrightMutation.isPending ||
            runJobQuery.data?.status === "pending" ||
            runJobQuery.data?.status === "running" ||
            eligiblePlaywrightClients.length === 0
          }
          onEdit={openEditForm}
          onCertificates={openCertificates}
          onValidate={openValidation}
          onDeactivate={(client) => void handleDeactivate(client)}
          actionDisabled={anyRowActionLoading}
        />
      ) : null}

      {view === "form" ? (
        <ClientForm
          mode={formMode}
          client={activeClient}
          isSubmitting={createClientMutation.isPending || updateClientMutation.isPending}
          errorMessage={formError}
          onSubmit={handleSubmitForm}
          onCancel={goToList}
        />
      ) : null}

      {view === "certificates" && activeClient ? (
        <CertificateUpload
          client={activeClient}
          isSubmitting={uploadCertificatesMutation.isPending}
          successMessage={certificateSuccess}
          errorMessage={certificateError}
          onUpload={handleUploadCertificates}
          onBack={goToList}
        />
      ) : null}

      {view === "validation" && activeClient ? (
        <ConfigValidationPanel
          client={activeClient}
          result={validationResult}
          isValidating={validateConfigMutation.isPending}
          errorMessage={validationError}
          onRevalidate={() => runValidation(activeClient)}
          onBack={goToList}
        />
      ) : null}

      <RunPlaywrightModal
        isOpen={runModalOpen}
        clients={eligiblePlaywrightClients}
        isSubmitting={runPlaywrightMutation.isPending}
        errorMessage={runError}
        onClose={() => setRunModalOpen(false)}
        onSubmit={handleRunPlaywright}
      />
    </main>
  );
}
