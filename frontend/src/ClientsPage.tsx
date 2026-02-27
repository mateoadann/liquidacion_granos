import { useEffect, useMemo, useState } from "react";
import CertificateUpload from "./CertificateUpload";
import CoeExportPanel from "./CoeExportPanel";
import ClientForm, { type ClientFormMode, type ClientFormValues } from "./ClientForm";
import ClientTable from "./ClientTable";
import ConfigValidationPanel from "./ConfigValidationPanel";
import RunPlaywrightModal from "./RunPlaywrightModal";
import type { Client, ClientValidationResult, PlaywrightPipelineRunResult } from "./clients";
import {
  useClientsQuery,
  useCreateClientMutation,
  useDownloadClientCoesMutation,
  usePlaywrightJobQuery,
  useDeleteClientMutation,
  useRunPlaywrightPipelineMutation,
  useUpdateClientMutation,
  useUploadCertificatesMutation,
  useValidateConfigMutation,
} from "./useClients";

type PageView = "list" | "form" | "certificates" | "validation" | "exports";

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
  const [exportError, setExportError] = useState<string | null>(null);
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
  const downloadClientCoesMutation = useDownloadClientCoesMutation();
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
    downloadClientCoesMutation.isPending ||
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

  function openExportCoes(client: Client) {
    setSelectedClient(client);
    setExportError(null);
    setView("exports");
  }

  async function handleDownloadCoes(
    format: "csv" | "xlsx",
    filters: { fechaDesde?: string; fechaHasta?: string }
  ) {
    if (!activeClient) return;
    setExportError(null);
    try {
      const file = await downloadClientCoesMutation.mutateAsync({
        clientId: activeClient.id,
        format,
        fechaDesde: filters.fechaDesde,
        fechaHasta: filters.fechaHasta,
      });

      const url = URL.createObjectURL(file.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = file.fileName;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);

      setMessage({
        type: "success",
        text: `Archivo generado: ${file.fileName}`,
      });
    } catch (error) {
      setExportError(getErrorMessage(error));
    }
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
      const job = await runPlaywrightMutation.mutateAsync(input);
      setRunJobId(job.id);
      setRunModalOpen(false);
      setMessage({
        type: "success",
        text: `Proceso Playwright encolado (job ${job.id}). Seguimiento en logs con 'make logs SERVICE=worker'.`,
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
              ? `Playwright finalizó con errores (${job.result.taxpayersOk}/${job.result.taxpayersTotal} clientes OK). Revisá logs con 'make logs SERVICE=worker'.`
              : `Playwright finalizó OK para ${job.result.taxpayersOk} cliente(s). Revisá logs con 'make logs SERVICE=worker'.`,
        });
      } else {
        setMessage({
          type: "error",
          text: `El job ${job.id} finalizó sin resultado. Revisá logs con 'make logs SERVICE=worker'.`,
        });
      }
      setLastNotifiedJobId(job.id);
      return;
    }

    if (job.status === "failed") {
      if (job.result) {
        setRunResult(job.result);
      }
      setMessage({
        type: "error",
        text: job.result
          ? `Playwright finalizó con errores (${job.result.taxpayersOk}/${job.result.taxpayersTotal} clientes OK). ${job.errorMessage ?? ""} Revisá logs con 'make logs SERVICE=worker'.`
          : `El job ${job.id} falló: ${job.errorMessage ?? "sin detalle"}. Revisá logs con 'make logs SERVICE=worker'.`,
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
          <h2 className="text-base font-semibold text-slate-900">Última corrida Playwright</h2>
          <p className="mt-1 text-sm text-slate-600">
            Rango: {runResult.fechaDesde} → {runResult.fechaHasta} · Clientes:{" "}
            {runResult.taxpayersTotal} · OK: {runResult.taxpayersOk} · Error:{" "}
            {runResult.taxpayersError}
          </p>
          <div className="mt-3 space-y-2">
            {runResult.results.map((item) => (
              <div
                key={item.taxpayerId}
                className={`rounded-md border px-3 py-2 text-sm ${
                  item.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-red-200 bg-red-50 text-red-800"
                }`}
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
            ))}
          </div>
        </section>
      ) : null}

      {runJobQuery.data ? (
        <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900">Job Playwright en segundo plano</h2>
          <p className="mt-1 text-sm text-slate-600">
            Job #{runJobQuery.data.id} · Estado: {runJobQuery.data.status}
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
                  {runJobQuery.data.progress.totalClients} clientes
                </p>
              </div>
              <div className="mt-3 space-y-2">
                {runJobQuery.data.progress.clients.map((clientProgress) => {
                  const statusClass =
                    clientProgress.status === "done"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : clientProgress.status === "error"
                        ? "border-red-200 bg-red-50 text-red-800"
                        : clientProgress.status === "running"
                          ? "border-blue-200 bg-blue-50 text-blue-800"
                          : "border-slate-200 bg-slate-50 text-slate-700";

                  return (
                    <div
                      key={clientProgress.taxpayerId}
                      className={`rounded-md border px-3 py-2 text-sm ${statusClass}`}
                    >
                      <p className="font-medium">
                        {clientProgress.empresa} (id {clientProgress.taxpayerId}) ·{" "}
                        {clientProgress.status}
                      </p>
                      {clientProgress.status === "done" || clientProgress.status === "error" ? (
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
          <p className="mt-1 text-sm text-slate-600">
            Logs en tiempo real: <code>make logs SERVICE=worker</code>
          </p>
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
          onExportCoes={openExportCoes}
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

      {view === "exports" && activeClient ? (
        <CoeExportPanel
          client={activeClient}
          isDownloading={downloadClientCoesMutation.isPending}
          errorMessage={exportError}
          onDownload={handleDownloadCoes}
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
