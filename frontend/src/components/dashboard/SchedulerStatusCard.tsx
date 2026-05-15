import { Card } from "../ui";
import { Spinner } from "../ui";
import { Badge } from "../ui";
import { formatDateTime } from "../../dateUtils";
import type { SchedulerStatus } from "../../api/scheduler";

interface SchedulerStatusCardProps {
  status: SchedulerStatus | undefined;
  isLoading: boolean;
  errorMessage?: string | null;
}

interface StatBlockProps {
  label: string;
  value: string | number;
  helper?: string;
  tone?: "default" | "success" | "warning" | "error";
}

const toneClasses: Record<NonNullable<StatBlockProps["tone"]>, string> = {
  default: "text-slate-900",
  success: "text-emerald-600",
  warning: "text-amber-600",
  error: "text-red-600",
};

function StatBlock({ label, value, helper, tone = "default" }: StatBlockProps) {
  return (
    <Card>
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${toneClasses[tone]}`}>{value}</p>
      {helper ? <p className="text-xs text-slate-400 mt-1">{helper}</p> : null}
    </Card>
  );
}

export function SchedulerStatusCard({
  status,
  isLoading,
  errorMessage,
}: SchedulerStatusCardProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <Card key={i} className="flex items-center justify-center h-24">
            <Spinner size="md" />
          </Card>
        ))}
      </div>
    );
  }

  const total = status?.taxpayers_total ?? 0;
  const activos = status?.taxpayers_activos_en_scheduler ?? 0;
  const errores = status?.con_error_reciente ?? [];
  const ultimoGlobal = status?.ultimo_scrape_global ?? null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatBlock
          label="Empresas activas"
          value={total}
          helper={`${activos} programadas`}
          tone="default"
        />
        <StatBlock
          label="Empresas programadas"
          value={activos}
          helper={
            total > 0
              ? `${Math.round((activos / total) * 100)}% del total`
              : undefined
          }
          tone="success"
        />
        <StatBlock
          label="Última consulta global"
          value={ultimoGlobal ? formatDateTime(ultimoGlobal) : "Sin registros"}
          tone={ultimoGlobal ? "default" : "warning"}
        />
      </div>

      {errorMessage ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {errorMessage}
        </div>
      ) : null}

      {errores.length > 0 ? (
        <Card>
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                Empresas con errores recientes
              </h3>
              <p className="text-sm text-slate-500">
                Últimos errores al consultar Arca.
              </p>
            </div>
            <Badge variant="error" size="md">
              {errores.length}
            </Badge>
          </div>
          <ul className="divide-y divide-slate-100">
            {errores.slice(0, 10).map((item) => (
              <li key={item.taxpayer_id} className="py-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-slate-800">
                    {item.empresa}
                  </span>
                  <span className="text-xs text-slate-500">
                    {item.ultimo_scrape_error_en
                      ? formatDateTime(item.ultimo_scrape_error_en)
                      : "-"}
                  </span>
                </div>
                <p className="text-sm text-red-700 mt-1 break-words">
                  {item.ultimo_scrape_error}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
