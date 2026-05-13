import { Badge } from "../ui";

export function JobStatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "success" | "warning" | "error" | "info"> = {
    pending: "warning",
    running: "info",
    completed: "success",
    failed: "error",
  };
  const labels: Record<string, string> = {
    pending: "Pendiente",
    running: "Ejecutando",
    completed: "Completado",
    failed: "Fallido",
  };
  return <Badge variant={variants[status] ?? "default"}>{labels[status] ?? status}</Badge>;
}
