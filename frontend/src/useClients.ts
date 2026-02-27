import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  createClient,
  deleteClient,
  downloadClientCoesExport,
  getPlaywrightPipelineJob,
  listClients,
  runPlaywrightPipeline,
  updateClient,
  uploadClientCertificates,
  validateClientConfig,
  type Client,
  type ClientCertificateMeta,
  type ClientValidationResult,
  type CreateClientInput,
  type DownloadClientCoesInput,
  type DownloadFileResult,
  type PlaywrightPipelineJob,
  type RunPlaywrightPipelineInput,
  type UpdateClientInput,
  type UploadCertificatesInput,
} from "./clients";

export const clientsQueryKeys = {
  all: ["clients"] as const,
  detail: (clientId: number) => ["clients", clientId] as const,
};

export function useClientsQuery() {
  return useQuery({
    queryKey: clientsQueryKeys.all,
    queryFn: listClients,
  });
}

export function useCreateClientMutation(): UseMutationResult<
  Client,
  Error,
  CreateClientInput
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createClient,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clientsQueryKeys.all });
    },
  });
}

interface UpdateClientMutationInput {
  clientId: number;
  input: UpdateClientInput;
}

export function useUpdateClientMutation(): UseMutationResult<
  Client,
  Error,
  UpdateClientMutationInput
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ clientId, input }) => updateClient(clientId, input),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: clientsQueryKeys.all });
      void queryClient.invalidateQueries({
        queryKey: clientsQueryKeys.detail(variables.clientId),
      });
    },
  });
}

export function useDeleteClientMutation(): UseMutationResult<void, Error, number> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteClient,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clientsQueryKeys.all });
    },
  });
}

export function useUploadCertificatesMutation(): UseMutationResult<
  ClientCertificateMeta,
  Error,
  UploadCertificatesInput
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: uploadClientCertificates,
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: clientsQueryKeys.all });
      void queryClient.invalidateQueries({
        queryKey: clientsQueryKeys.detail(variables.clientId),
      });
    },
  });
}

export function useValidateConfigMutation(): UseMutationResult<
  ClientValidationResult,
  Error,
  number
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: validateClientConfig,
    onSuccess: (_, clientId) => {
      void queryClient.invalidateQueries({ queryKey: clientsQueryKeys.all });
      void queryClient.invalidateQueries({
        queryKey: clientsQueryKeys.detail(clientId),
      });
    },
  });
}

export function useRunPlaywrightPipelineMutation(): UseMutationResult<
  PlaywrightPipelineJob,
  Error,
  RunPlaywrightPipelineInput
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: runPlaywrightPipeline,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clientsQueryKeys.all });
    },
  });
}

export function usePlaywrightJobQuery(jobId: number | null): UseQueryResult<PlaywrightPipelineJob, Error> {
  return useQuery({
    queryKey: ["playwright-job", jobId],
    queryFn: () => {
      if (!jobId) {
        throw new Error("job_id inválido");
      }
      return getPlaywrightPipelineJob(jobId);
    },
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return 3000;
      if (status === "pending" || status === "running") return 3000;
      return false;
    },
  });
}

export function useDownloadClientCoesMutation(): UseMutationResult<
  DownloadFileResult,
  Error,
  DownloadClientCoesInput
> {
  return useMutation({
    mutationFn: downloadClientCoesExport,
  });
}
