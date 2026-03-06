import { Card, CardHeader, Badge, Spinner } from "../ui";
import { useJobsQuery } from "../../hooks/useJobs";

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function JobStatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "success" | "warning" | "error" | "info"> = {
    pending: "warning",
    running: "info",
    completed: "success",
    failed: "error",
  };
  const labels: Record<string, string> = {
    pending: "Pendiente",
    running: "Ejecutando",
    completed: "Completado",
    failed: "Fallido",
  };
  return <Badge variant={variants[status] ?? "default"}>{labels[status] ?? status}</Badge>;
}

export function RecentJobsPanel() {
  const jobsQuery = useJobsQuery({ limit: 10 });
  const jobs = jobsQuery.data?.jobs ?? [];

  return (
    <Card padding="lg">
      <CardHeader
        title="Extracciones Recientes"
        subtitle="Últimas 10 ejecuciones de Playwright"
      />

      {jobsQuery.isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">
          No hay extracciones registradas
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                <th className="text-left py-2 px-2 font-medium text-slate-600">ID</th>
                <th className="text-left py-2 px-2 font-medium text-slate-600">Fecha</th>
                <th className="text-left py-2 px-2 font-medium text-slate-600">Estado</th>
                <th className="text-left py-2 px-2 font-medium text-slate-600">Duración</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const duration =
                  job.started_at && job.finished_at
                    ? Math.round(
                        (new Date(job.finished_at).getTime() -
                          new Date(job.started_at).getTime()) /
                          1000
                      )
                    : null;

                return (
                  <tr key={job.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-2 px-2 text-slate-900">#{job.id}</td>
                    <td className="py-2 px-2 text-slate-600">
                      {formatDate(job.created_at)}
                    </td>
                    <td className="py-2 px-2">
                      <JobStatusBadge status={job.status} />
                    </td>
                    <td className="py-2 px-2 text-slate-600">
                      {duration !== null ? `${duration}s` : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
