import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkUpdateScheduler,
  getSchedulerStatus,
  patchTaxpayerScheduler,
  runSchedulerNow,
  type BulkSchedulerConfig,
  type BulkSchedulerResponse,
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

export function useBulkUpdateSchedulerMutation() {
  const queryClient = useQueryClient();
  return useMutation<
    BulkSchedulerResponse,
    Error,
    { taxpayerIds: number[]; config: BulkSchedulerConfig }
  >({
    mutationFn: ({ taxpayerIds, config }) => bulkUpdateScheduler(taxpayerIds, config),
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
