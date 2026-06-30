import type { Coe } from "../api/coes";

/**
 * Tri-state control indicator combining the manual `controlada` flag with the
 * RPA reconciliation verdict (`control_rpa_estado`).
 *
 * Priority: an RPA verdict (ok / inconsistente) wins the color; otherwise the
 * manual flag drives a neutral check. The mismatch detail lives in the
 * carga_inconsistente gestion — here we only surface the verdict + a tooltip.
 */
export function ControlIndicator({ coe }: { coe: Coe }) {
  const rpa = coe.control_rpa_estado;

  if (rpa === "ok") {
    return <Mark color="text-green-600 border-green-600" title="Control OK (RPA)" />;
  }
  if (rpa === "inconsistente") {
    return (
      <Mark
        color="text-red-600 border-red-600"
        title="Control fallido (RPA) — hay diferencias. Ver gestión de carga inconsistente."
      />
    );
  }
  if (coe.controlada) {
    return <Mark color="text-slate-700 border-slate-400" title="Controlado manualmente" />;
  }
  return (
    <input
      type="checkbox"
      checked={false}
      disabled
      aria-label="sin controlar"
      title={rpa === "no_encontrado" ? "RPA: COE no encontrado en Holistor" : "Sin controlar"}
      className="form-checkbox h-4 w-4 rounded border-slate-300"
    />
  );
}

function Mark({ color, title }: { color: string; title: string }) {
  return (
    <span
      title={title}
      aria-label={title}
      className={`inline-flex h-4 w-4 items-center justify-center rounded border-2 text-xs font-bold ${color}`}
    >
      ✓
    </span>
  );
}
