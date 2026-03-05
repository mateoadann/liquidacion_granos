import { useQuery } from "@tanstack/react-query";
import { listJobs, getJob, type Job, type JobsListResponse } from "../api/jobs";

export function useJobsQuery(params?: { status?: string; limit?: number }) {
  return useQuery<JobsListResponse, Error>({
    queryKey: ["jobs", params],
    queryFn: () => listJobs(params),
    refetchInterval: (query) => {
      // Si hay jobs pending/running, refrescar más seguido
      const data = query.state.data;
      if (data?.jobs.some((j) => j.status === "pending" || j.status === "running")) {
        return 3000;
      }
      return 30000;
    },
    staleTime: 5000,
  });
}

export function useJobQuery(id: number | null) {
  return useQuery<Job, Error>({
    queryKey: ["job", id],
    queryFn: () => getJob(id!),
    enabled: id !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "pending" || status === "running") {
        return 3000;
      }
      return false;
    },
  });
}
