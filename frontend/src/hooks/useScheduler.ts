import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkUpdateScheduler,
  getLastErrorDetail,
  getSchedulerStatus,
  patchTaxpayerScheduler,
  runSchedulerNow,
  type BulkSchedulerBody,
  type BulkSchedulerResponse,
  type LastErrorDetail,
  type PatchSchedulerBody,
  type RunNowResponse,
  type SchedulerConfig,
  type SchedulerStatus,
} from "../api/scheduler";

export function useSchedulerStatusQuery() {
  return useQuery<SchedulerStatus, Error>({
    queryKey: ["scheduler", "status"],
    queryFn: getSchedulerStatus,
    refetchInterval: 30000,
  });
}

export function useUpdateTaxpayerSchedulerMutation() {
  const queryClient = useQueryClient();
  return useMutation<
    SchedulerConfig,
    Error,
    { taxpayerId: number; body: PatchSchedulerBody }
  >({
    mutationFn: ({ taxpayerId, body }) => patchTaxpayerScheduler(taxpayerId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scheduler"] });
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });
}

export function useRunSchedulerNowMutation() {
  const queryClient = useQueryClient();
  return useMutation<RunNowResponse, Error, number>({
    mutationFn: (taxpayerId: number) => runSchedulerNow(taxpayerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scheduler"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useBulkUpdateSchedulerMutation() {
  const queryClient = useQueryClient();
  return useMutation<BulkSchedulerResponse, Error, BulkSchedulerBody>({
    mutationFn: (body) => bulkUpdateScheduler(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scheduler"] });
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });
}

export function useLastErrorDetailQuery(
  taxpayerId: number | null,
  enabled: boolean,
) {
  return useQuery<LastErrorDetail, Error>({
    queryKey: ["scheduler", "last-error-detail", taxpayerId],
    queryFn: () => getLastErrorDetail(taxpayerId as number),
    enabled: enabled && taxpayerId !== null,
  });
}
