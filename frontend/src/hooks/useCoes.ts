import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  consultManualCoe,
  createManualCoe,
  getCoe,
  listCoes,
  type Coe,
  type CoesListParams,
  type CoesListResponse,
  type ConsultManualCoeRequest,
  type ConsultManualCoeResponse,
  type CreateManualCoeRequest,
} from "../api/coes";

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

export function useConsultManualCoe() {
  return useMutation<ConsultManualCoeResponse, Error, ConsultManualCoeRequest>({
    mutationFn: consultManualCoe,
  });
}

export function useCreateManualCoe() {
  const qc = useQueryClient();
  return useMutation<Coe, Error, CreateManualCoeRequest>({
    mutationFn: createManualCoe,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["coes"] });
    },
  });
}
