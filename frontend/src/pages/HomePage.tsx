import { useAuthStore } from "../store/useAuthStore";
import { useStatsQuery } from "../hooks/useStats";
import { StatsCards, PlaywrightPanel, RecentJobsPanel } from "../components/dashboard";

export function HomePage() {
  const { user } = useAuthStore();
  const statsQuery = useStatsQuery();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">
          Bienvenido, {user?.nombre}
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Panel de Control - Sistema de liquidación de granos
        </p>
      </div>

      {/* Stats Cards */}
      <StatsCards stats={statsQuery.data} isLoading={statsQuery.isLoading} />

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Panel de Playwright */}
        <PlaywrightPanel />

        {/* Jobs recientes */}
        <RecentJobsPanel />
      </div>
    </div>
  );
}
