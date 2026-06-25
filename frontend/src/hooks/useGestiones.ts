import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listGestiones,
  marcarGestionRealizada,
  type Gestion,
  type GestionesListParams,
  type GestionesListResponse,
} from "../api/gestiones";

export function useGestionesQuery(params?: GestionesListParams) {
  return useQuery<GestionesListResponse, Error>({
    queryKey: ["gestiones", params],
    queryFn: () => listGestiones(params),
    staleTime: 15000,
  });
}

export function useMarcarGestionMutation() {
  const qc = useQueryClient();
  return useMutation<Gestion, Error, string>({
    mutationFn: (gestionId: string) => marcarGestionRealizada(gestionId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["gestiones"] });
    },
  });
}
