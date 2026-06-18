import { useState } from "react";
import { useAuthStore } from "../store/useAuthStore";
import { useStatsQuery, useMonthlyStatsQuery } from "../hooks/useStats";
import { StatsCards, PlaywrightPanel, RecentJobsPanel } from "../components/dashboard";

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function currentMonthYear(): { mes: number; anio: number } {
  const now = new Date();
  return { mes: now.getMonth() + 1, anio: now.getFullYear() };
}

function prevMonth(mes: number, anio: number): { mes: number; anio: number } {
  return mes === 1 ? { mes: 12, anio: anio - 1 } : { mes: mes - 1, anio };
}

function nextMonth(mes: number, anio: number): { mes: number; anio: number } {
  return mes === 12 ? { mes: 1, anio: anio + 1 } : { mes: mes + 1, anio };
}

export function HomePage() {
  const { user } = useAuthStore();
  const statsQuery = useStatsQuery();

  const [{ mes, anio }, setMonthYear] = useState(currentMonthYear);

  const monthlyQuery = useMonthlyStatsQuery(mes, anio);

  const monthLabel = `${MONTH_NAMES[mes - 1]} ${anio}`;

  return (
    <div className="space-y-6">
      {/* Header con selector de período */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Bienvenido, {user?.nombre}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Panel de Control - Sistema de liquidación de granos
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-slate-600">Período</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setMonthYear(prevMonth(mes, anio))}
              className="p-1 rounded hover:bg-slate-100 text-slate-600 transition-colors"
              aria-label="Mes anterior"
            >
              ←
            </button>
            <span className="text-sm font-semibold text-slate-800 min-w-[140px] text-center">
              {monthLabel}
            </span>
            <button
              onClick={() => setMonthYear(nextMonth(mes, anio))}
              className="p-1 rounded hover:bg-slate-100 text-slate-600 transition-colors"
              aria-label="Mes siguiente"
            >
              →
            </button>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <StatsCards
        stats={statsQuery.data}
        isLoading={statsQuery.isLoading}
        monthlyStats={monthlyQuery.data}
        isLoadingMonthly={monthlyQuery.isLoading}
        monthLabel={monthLabel}
      />

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
