import { useState } from "react";
import { Card, CardHeader, Spinner } from "../ui";
import { useJobsQuery } from "../../hooks/useJobs";
import { formatDateTime } from "../../dateUtils";
import { JobDetailDrawer } from "./JobDetailDrawer";
import { JobStatusBadge } from "./JobStatusBadge";

export function RecentJobsPanel() {
  const jobsQuery = useJobsQuery({ limit: 10 });
  const jobs = jobsQuery.data?.jobs ?? [];
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);

  const selectedJob = selectedJobId !== null ? jobs.find((j) => j.id === selectedJobId) ?? null : null;

  return (
    <Card padding="lg">
      <CardHeader
        title="Extracciones Recientes"
        subtitle="Últimas 10 ejecuciones de extracción."
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
                <th className="text-left py-2 px-2 font-medium text-slate-600">COEs</th>
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
                  <tr
                    key={job.id}
                    onClick={() => setSelectedJobId(job.id)}
                    className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="py-2 px-2 text-slate-900">#{job.id}</td>
                    <td className="py-2 px-2 text-slate-600">
                      {formatDateTime(job.created_at)}
                    </td>
                    <td className="py-2 px-2">
                      <JobStatusBadge status={job.status} />
                    </td>
                    <td className="py-2 px-2 text-slate-600">
                      {job.coe_count > 0 ? job.coe_count : "-"}
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

      <JobDetailDrawer job={selectedJob} onClose={() => setSelectedJobId(null)} />
    </Card>
  );
}
