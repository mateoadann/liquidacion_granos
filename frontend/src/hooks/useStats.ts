import { useQuery } from "@tanstack/react-query";
import { getStats, type DashboardStats } from "../api/stats";

export function useStatsQuery() {
  return useQuery<DashboardStats, Error>({
    queryKey: ["stats"],
    queryFn: getStats,
    refetchInterval: 30000, // Refrescar cada 30 segundos
    staleTime: 10000,
  });
}
