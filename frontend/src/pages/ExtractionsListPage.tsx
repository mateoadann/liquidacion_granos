import { useState } from "react";
import { PageHeader } from "../components/layout";
import {
  Card,
  Spinner,
  Alert,
  Select,
  Combobox,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableCell,
  Pagination,
} from "../components/ui";
import { useJobsPaginatedQuery } from "../hooks/useJobs";
import { useClientsQuery } from "../useClients";
import { usePageQueryParam } from "../hooks/usePageQueryParam";
import { formatDateTime } from "../dateUtils";
import { JobDetailDrawer } from "../components/dashboard/JobDetailDrawer";
import { JobStatusBadge } from "../components/dashboard/JobStatusBadge";
import { operationLabel } from "../api/jobs";

const STATUS_OPTIONS = [
  { value: "", label: "Todos los estados" },
  { value: "pending", label: "Pendiente" },
  { value: "running", label: "En ejecución" },
  { value: "completed", label: "Completado" },
  { value: "partial", label: "Parcial" },
  { value: "failed", label: "Con error" },
];

export function ExtractionsListPage() {
  const [page, setPage] = usePageQueryParam();
  const [status, setStatus] = useState<string>("");
  const [taxpayerId, setTaxpayerId] = useState<number | undefined>();
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);

  const clientsQuery = useClientsQuery();
  const jobsQuery = useJobsPaginatedQuery({
    page,
    per_page: 20,
    status: status || undefined,
    taxpayer_id: taxpayerId,
  });

  const clients = clientsQuery.data ?? [];
  const jobs = jobsQuery.data?.jobs ?? [];
  const selectedJob =
    selectedJobId !== null ? jobs.find((j) => j.id === selectedJobId) ?? null : null;

  function handleStatusChange(value: string) {
    setStatus(value);
    setPage(1);
  }

  function handleTaxpayerChange(value: string) {
    setTaxpayerId(value ? Number(value) : undefined);
    setPage(1);
  }

  return (
    <div>
      <PageHeader
        title="Extracciones"
        subtitle="Historial completo de ejecuciones de extracción"
      />

      <Card>
        <div className="flex flex-wrap items-center gap-3 p-4 border-b border-slate-200">
          <div className="flex-1 min-w-[200px]">
            <Combobox
              value={taxpayerId !== undefined ? String(taxpayerId) : ""}
              onChange={handleTaxpayerChange}
              options={[
                { value: "", label: "Todos los clientes" },
                ...clients.map((c) => ({
                  value: String(c.id),
                  label: c.empresa,
                })),
              ]}
              placeholder="Filtrar por cliente"
            />
          </div>
          <div className="min-w-[180px]">
            <Select
              value={status}
              onChange={(e) => handleStatusChange(e.target.value)}
              options={STATUS_OPTIONS}
            />
          </div>
        </div>

        {jobsQuery.isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : jobsQuery.isError ? (
          <div className="p-4">
            <Alert variant="error">Error al cargar extracciones</Alert>
          </div>
        ) : jobs.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            No se encontraron extracciones
          </div>
        ) : (
          <>
            {jobsQuery.data && jobsQuery.data.pages > 1 ? (
              <Pagination
                page={jobsQuery.data.page}
                pages={jobsQuery.data.pages}
                total={jobsQuery.data.total}
                perPage={jobsQuery.data.per_page}
                onPageChange={setPage}
              />
            ) : null}

            <Table>
              <TableHeader>
                <TableRow>
                  <TableCell header>ID</TableCell>
                  <TableCell header>Fecha</TableCell>
                  <TableCell header>Cliente</TableCell>
                  <TableCell header>Operación</TableCell>
                  <TableCell header>Estado</TableCell>
                  <TableCell header>COEs</TableCell>
                  <TableCell header>Duración</TableCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => {
                  const duration =
                    job.started_at && job.finished_at
                      ? Math.round(
                          (new Date(job.finished_at).getTime() -
                            new Date(job.started_at).getTime()) /
                            1000,
                        )
                      : null;
                  const taxpayer = clients.find((c) => c.id === job.taxpayer_id);
                  return (
                    <TableRow
                      key={job.id}
                      onClick={() => setSelectedJobId(job.id)}
                      className="cursor-pointer hover:bg-slate-50"
                    >
                      <TableCell>#{job.id}</TableCell>
                      <TableCell>{formatDateTime(job.created_at)}</TableCell>
                      <TableCell>{taxpayer?.empresa ?? "—"}</TableCell>
                      <TableCell>{operationLabel(job.operation)}</TableCell>
                      <TableCell>
                        <JobStatusBadge status={job.status} />
                      </TableCell>
                      <TableCell>{job.coe_count > 0 ? job.coe_count : "-"}</TableCell>
                      <TableCell>{duration !== null ? `${duration}s` : "-"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>

            {jobsQuery.data && jobsQuery.data.pages > 1 ? (
              <Pagination
                page={jobsQuery.data.page}
                pages={jobsQuery.data.pages}
                total={jobsQuery.data.total}
                perPage={jobsQuery.data.per_page}
                onPageChange={setPage}
              />
            ) : null}
          </>
        )}
      </Card>

      <JobDetailDrawer job={selectedJob} onClose={() => setSelectedJobId(null)} />
    </div>
  );
}
