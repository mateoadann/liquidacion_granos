import { useQuery } from "@tanstack/react-query";
import { getStats, fetchMonthlyStats, type DashboardStats, type MonthlyStats } from "../api/stats";

export function useStatsQuery() {
  return useQuery<DashboardStats, Error>({
    queryKey: ["stats"],
    queryFn: getStats,
    refetchInterval: 30000, // Refrescar cada 30 segundos
    staleTime: 10000,
  });
}

export function useMonthlyStatsQuery(mes: number, anio: number) {
  return useQuery<MonthlyStats, Error>({
    queryKey: ["stats", "mensual", mes, anio],
    queryFn: () => fetchMonthlyStats(mes, anio),
    refetchInterval: 30000,
    staleTime: 10000,
  });
}
