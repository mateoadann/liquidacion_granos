import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listCoes, getCoe, toggleCoeControlada, type Coe, type CoesListResponse, type CoesListParams } from "../api/coes";

export function useCoesQuery(params?: CoesListParams) {
  return useQuery<CoesListResponse, Error>({
    queryKey: ["coes", params],
    queryFn: () => listCoes(params),
    staleTime: 30000,
  });
}

export function useCoeQuery(id: number | null) {
  return useQuery<Coe, Error>({
    queryKey: ["coe", id],
    queryFn: () => getCoe(id!),
    enabled: id !== null && id > 0,
  });
}

interface ToggleControladaContext {
  prev: Coe | undefined;
}

export function useToggleCoeControladaMutation() {
  const qc = useQueryClient();
  return useMutation<Coe, Error, { id: number; controlada: boolean }, ToggleControladaContext>({
    mutationFn: ({ id, controlada }) => toggleCoeControlada(id, controlada),
    onMutate: async ({ id, controlada }) => {
      await qc.cancelQueries({ queryKey: ["coe", id] });
      const prev = qc.getQueryData<Coe>(["coe", id]);
      if (prev) {
        qc.setQueryData<Coe>(["coe", id], { ...prev, controlada });
      }
      return { prev };
    },
    onError: (_err, { id }, ctx) => {
      if (ctx?.prev) {
        qc.setQueryData(["coe", id], ctx.prev);
      }
    },
    onSettled: (_data, _err, { id }) => {
      qc.invalidateQueries({ queryKey: ["coe", id] });
      qc.invalidateQueries({ queryKey: ["coes"] });
    },
  });
}
