import { useQuery } from "@tanstack/react-query";
import { getPersona, type PersonaInfo } from "../api/padron";

export function usePersonaQuery(cuit: string | null | undefined, taxpayerId: number | null | undefined) {
  const sanitized = cuit ? String(cuit).replace(/\D/g, "") : "";
  return useQuery<PersonaInfo, Error>({
    queryKey: ["persona", sanitized, taxpayerId],
    queryFn: () => getPersona(sanitized, taxpayerId!),
    enabled: sanitized.length === 11 && !!taxpayerId,
    staleTime: 5 * 60 * 1000, // 5 min cache
    retry: 1,
  });
}
