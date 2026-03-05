import { useQuery } from "@tanstack/react-query";
import { listCoes, getCoe, type Coe, type CoesListResponse, type CoesListParams } from "../api/coes";

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
