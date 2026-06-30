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
    return (
      <span
        title="Control OK (RPA)"
        aria-label="Control OK (RPA)"
        className="inline-flex h-4 w-4 items-center justify-center rounded bg-green-600 text-xs font-bold text-white"
      >
        ✓
      </span>
    );
  }
  if (rpa === "inconsistente") {
    return (
      <span
        title="Control fallido (RPA) — hay diferencias. Ver gestión de carga inconsistente."
        aria-label="Control fallido (RPA)"
        className="inline-flex h-4 w-4 items-center justify-center rounded bg-red-600 text-xs font-bold text-white"
      >
        ✓
      </span>
    );
  }
  // Manual control (or none) — native checkbox, neutral color, same as before.
  return (
    <input
      type="checkbox"
      checked={coe.controlada}
      disabled
      aria-label={coe.controlada ? "Controlado manualmente" : "sin controlar"}
      title={
        coe.controlada
          ? "Controlado manualmente"
          : rpa === "no_encontrado"
            ? "RPA: COE no encontrado en Holistor"
            : "Sin controlar"
      }
      className="form-checkbox h-4 w-4 rounded border-slate-300"
    />
  );
}
