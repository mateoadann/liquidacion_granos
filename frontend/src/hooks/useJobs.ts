import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listJobs,
  listJobsPaginated,
  getJob,
  retryJob,
  type Job,
  type JobsListResponse,
  type JobsPaginatedResponse,
} from "../api/jobs";

export function useJobsQuery(params?: { status?: string; limit?: number }) {
  return useQuery<JobsListResponse, Error>({
    queryKey: ["jobs", params],
    queryFn: () => listJobs(params),
    refetchInterval: (query) => {
      // Si hay jobs pending/running, refrescar más seguido
      const data = query.state.data;
      if (data && data.jobs.some((j) => j.status === "pending" || j.status === "running")) {
        return 3000;
      }
      return 30000;
    },
    staleTime: 5000,
  });
}

export function useJobsPaginatedQuery(params: {
  page: number;
  per_page?: number;
  status?: string;
  taxpayer_id?: number;
}) {
  return useQuery<JobsPaginatedResponse, Error>({
    queryKey: ["jobs-paginated", params],
    queryFn: () => listJobsPaginated(params),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && data.jobs.some((j) => j.status === "pending" || j.status === "running")) {
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

export function useRetryJobMutation() {
  const queryClient = useQueryClient();
  return useMutation<Job, Error, number>({
    mutationFn: (jobId: number) => retryJob(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs-paginated"] });
    },
  });
}

/**
 * Mirror del classifier del backend (`backend/app/services/failure_classifier.py`).
 * Si esto se desincroniza, el botón puede mostrarse para un caso que el
 * backend rechazará con 409 (no es crítico, pero indeseable).
 */
const RETRYABLE_ERROR_TYPES = new Set(["timeout", "network", "arca_unavailable", "unknown"]);
const NON_RETRYABLE_ERROR_TYPES = new Set(["auth_failed"]);

export function isJobRetryableInUI(job: Job): boolean {
  if (job.status !== "failed") return false;
  const errorType = (job.payload as Record<string, unknown> | null)?.["failure_error_type"];
  if (typeof errorType === "string") {
    if (NON_RETRYABLE_ERROR_TYPES.has(errorType)) return false;
    if (RETRYABLE_ERROR_TYPES.has(errorType)) return true;
  }
  // Sin error_type: si no hay phase tampoco, conservador-permisivo (DOM flake).
  if (!job.failure_phase) return true;
  // Phase pero sin error_type conocido → no mostrar el botón.
  return false;
}
