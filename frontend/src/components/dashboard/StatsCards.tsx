import { Card } from "../ui";
import { Spinner } from "../ui";
import type { DashboardStats } from "../../api/stats";

interface StatsCardsProps {
  stats: DashboardStats | undefined;
  isLoading: boolean;
}

interface StatCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  color?: "green" | "amber" | "red" | "blue" | "slate";
}

function StatCard({ title, value, subtitle, color = "slate" }: StatCardProps) {
  const colorClasses = {
    green: "text-green-600",
    amber: "text-amber-600",
    red: "text-red-600",
    blue: "text-blue-600",
    slate: "text-slate-900",
  };

  return (
    <Card>
      <p className="text-sm font-medium text-slate-500">{title}</p>
      <p className={`text-3xl font-bold mt-1 ${colorClasses[color]}`}>
        {value}
      </p>
      {subtitle ? (
        <p className="text-xs text-slate-400 mt-1">{subtitle}</p>
      ) : null}
    </Card>
  );
}

export function StatsCards({ stats, isLoading }: StatsCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="flex items-center justify-center h-24">
            <Spinner size="md" />
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        title="Clientes Activos"
        value={stats?.clients_active ?? 0}
        subtitle={`${stats?.clients_inactive ?? 0} inactivos`}
        color="green"
      />
      <StatCard
        title="COEs Totales"
        value={stats?.coes_total ?? 0}
        color="blue"
      />
      <StatCard
        title="Extracciones Exitosas"
        value={stats?.jobs_completed ?? 0}
        subtitle={`${stats?.jobs_failed ?? 0} fallidas`}
        color="green"
      />
      <StatCard
        title="En Proceso"
        value={(stats?.jobs_pending ?? 0) + (stats?.jobs_running ?? 0)}
        subtitle={stats?.jobs_running ? `${stats.jobs_running} ejecutando` : undefined}
        color="amber"
      />
    </div>
  );
}
