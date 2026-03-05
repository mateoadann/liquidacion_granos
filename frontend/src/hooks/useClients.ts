import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listClients,
  runPlaywrightPipeline,
  getPlaywrightPipelineJob,
  type Client,
  type PlaywrightPipelineJob,
  type RunPlaywrightPipelineInput,
} from "../clients";

export function useClientsQuery() {
  return useQuery<Client[], Error>({
    queryKey: ["clients"],
    queryFn: listClients,
  });
}

export function usePlaywrightJobQuery(jobId: number | null) {
  return useQuery<PlaywrightPipelineJob, Error>({
    queryKey: ["playwright-job", jobId],
    queryFn: () => getPlaywrightPipelineJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "pending" || status === "running") {
        return 3000;
      }
      return false;
    },
  });
}

export function useRunPlaywrightMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: RunPlaywrightPipelineInput) => runPlaywrightPipeline(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}
