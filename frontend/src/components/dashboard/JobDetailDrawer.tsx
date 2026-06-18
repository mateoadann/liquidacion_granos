import { Alert, Badge, Button, Drawer } from "../ui";
import { formatDateTime } from "../../dateUtils";
import type { Job } from "../../api/jobs";
import { operationLabel } from "../../api/jobs";
import { JobStatusBadge } from "./JobStatusBadge";
import { isJobRetryableInUI, useRetryJobMutation } from "../../hooks/useJobs";

interface JobDetailDrawerProps {
  job: Job | null;
  onClose: () => void;
}

function computeDuration(job: Job): string {
  if (job.started_at && job.finished_at) {
    const seconds = Math.round(
      (new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000
    );
    return `${seconds}s`;
  }
  if (job.status === "running" && job.started_at) {
    return "En curso";
  }
  return "-";
}

function MetadataRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 border-b border-slate-100 last:border-b-0">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</span>
      <span className="text-sm text-slate-900 text-right">{value}</span>
    </div>
  );
}

export function JobDetailDrawer({ job, onClose }: JobDetailDrawerProps) {
  const isOpen = job !== null;
  const title = job ? `Extracción #${job.id}` : "Extracción";
  const retryMutation = useRetryJobMutation();
  const canRetry = job ? isJobRetryableInUI(job) : false;

  const handleRetry = async () => {
    if (!job) return;
    try {
      await retryMutation.mutateAsync(job.id);
      onClose();
    } catch {
      // Error queda visible en el alert del bloque retry.
    }
  };

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title={title} width="lg">
      {job ? (
        <div className="space-y-6">
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-700">Información general</h3>
              <JobStatusBadge status={job.status} />
            </div>
            <div className="rounded-md border border-slate-200 px-3 py-2">
              <MetadataRow label="Operación" value={operationLabel(job.operation)} />
              <MetadataRow
                label="Cliente"
                value={job.taxpayer_id !== null ? `#${job.taxpayer_id}` : "-"}
              />
              <MetadataRow label="Creado" value={formatDateTime(job.created_at)} />
              <MetadataRow label="Iniciado" value={formatDateTime(job.started_at)} />
              <MetadataRow label="Finalizado" value={formatDateTime(job.finished_at)} />
              <MetadataRow label="Duración" value={computeDuration(job)} />
              {job.coe_count > 0 ? (
                <MetadataRow label="COEs extraídos" value={job.coe_count} />
              ) : null}
            </div>
          </section>

          {job.status === "running" && job.current_message ? (
            <section>
              <h3 className="text-sm font-semibold text-slate-700 mb-2">Progreso actual</h3>
              <Alert variant="info">
                {job.current_phase ? (
                  <div className="mb-2">
                    <span className="text-xs font-medium text-slate-500 mr-2">Fase:</span>
                    <code className="text-xs bg-white px-1.5 py-0.5 rounded border border-blue-200">
                      {job.current_phase}
                    </code>
                  </div>
                ) : null}
                <p>{job.current_message}</p>
              </Alert>
            </section>
          ) : null}

          {job.status === "failed" ? (
            <section>
              <h3 className="text-sm font-semibold text-slate-700 mb-2">Causa del error</h3>
              <Alert variant="error">
                <p className="font-medium mb-1">
                  {job.failure_message_user ??
                    job.error_message ??
                    "No hay información disponible."}
                </p>
                {job.failure_phase ? (
                  <div className="mt-2">
                    <span className="text-xs text-slate-500 mr-2">Fase:</span>
                    <code className="text-xs bg-white px-1.5 py-0.5 rounded border border-red-200">
                      {job.failure_phase}
                    </code>
                  </div>
                ) : null}
              </Alert>
              {job.failure_message_technical ? (
                <details className="mt-3 rounded-md border border-slate-200 px-3 py-2">
                  <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900">
                    Detalle técnico
                  </summary>
                  <pre className="mt-2 text-xs text-slate-600 whitespace-pre-wrap break-all">
                    {job.failure_message_technical}
                  </pre>
                </details>
              ) : null}

              {canRetry ? (
                <div className="mt-3 flex flex-col items-end gap-2">
                  {retryMutation.isError ? (
                    <Alert variant="error">
                      {retryMutation.error instanceof Error
                        ? retryMutation.error.message
                        : "No se pudo reintentar el job."}
                    </Alert>
                  ) : null}
                  <Button
                    variant="secondary"
                    onClick={handleRetry}
                    isLoading={retryMutation.isPending}
                  >
                    Reintentar
                  </Button>
                </div>
              ) : null}
            </section>
          ) : null}

          {job.status === "completed" ? (
            <section>
              <Alert variant="success">
                <p className="font-medium">Extracción completada exitosamente</p>
                {job.coe_count > 0 ? (
                  <p className="mt-1 text-sm">Se extrajeron {job.coe_count} COEs.</p>
                ) : null}
              </Alert>
            </section>
          ) : null}

          {job.status === "partial" ? (
            <section>
              <h3 className="text-sm font-semibold text-slate-700 mb-2">Resultado parcial</h3>
              <Alert variant="warning">
                <p className="font-medium mb-1">
                  Algunos clientes no pudieron procesarse. Revisá el detalle por cliente.
                </p>
                {job.failure_message_user ? (
                  <p className="mt-2 text-sm">{job.failure_message_user}</p>
                ) : null}
                {job.failure_phase ? (
                  <div className="mt-2">
                    <span className="text-xs text-slate-500 mr-2">Fase:</span>
                    <code className="text-xs bg-white px-1.5 py-0.5 rounded border border-amber-200">
                      {job.failure_phase}
                    </code>
                  </div>
                ) : null}
              </Alert>
              {job.failure_message_technical ? (
                <details className="mt-3 rounded-md border border-slate-200 px-3 py-2">
                  <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900">
                    Detalle técnico
                  </summary>
                  <pre className="mt-2 text-xs text-slate-600 whitespace-pre-wrap break-all">
                    {job.failure_message_technical}
                  </pre>
                </details>
              ) : null}
            </section>
          ) : null}

          {job.status === "pending" ? (
            <section>
              <Alert variant="warning">
                <p>La extracción está pendiente de ejecución.</p>
              </Alert>
            </section>
          ) : null}

          {job.payload && Object.keys(job.payload).length > 0 ? (
            <details className="rounded-md border border-slate-200 px-3 py-2">
              <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900">
                Payload
              </summary>
              <pre className="mt-2 text-xs text-slate-600 whitespace-pre-wrap break-all">
                {JSON.stringify(job.payload, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      ) : (
        <div className="flex justify-center py-8">
          <Badge>Sin selección</Badge>
        </div>
      )}
    </Drawer>
  );
}
