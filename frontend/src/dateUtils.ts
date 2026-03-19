const TZ = "America/Argentina/Cordoba";

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "-";
  const date = typeof value === "string" ? new Date(value) : value;
  if (isNaN(date.getTime())) return "-";
  return date.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: TZ,
  });
}

/**
 * For date-only strings (YYYY-MM-DD), append T12:00:00 to avoid
 * timezone offset shifting the displayed date to the previous day.
 */
function safeParseDateOnly(value: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Date(`${value}T12:00:00`);
  }
  return new Date(value);
}

export function formatDateOnly(value: string | Date | null | undefined): string {
  if (!value) return "-";
  const date = typeof value === "string" ? safeParseDateOnly(value) : value;
  if (isNaN(date.getTime())) return "-";
  return date.toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: TZ,
  });
}
