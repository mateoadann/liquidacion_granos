import { useEffect, useRef, useState } from "react";
import { DayPicker } from "react-day-picker";
import { es } from "date-fns/locale";
import "react-day-picker/dist/style.css";

interface DatePickerProps {
  label?: string;
  value: string;
  onChange: (isoDate: string) => void;
  disabled?: boolean;
  error?: string;
  helperText?: string;
  id?: string;
  min?: string;
  max?: string;
}

function isoToDDMMYYYY(iso: string): string {
  if (!iso) return "";
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  const [y, m, d] = parts;
  return `${d}/${m}/${y}`;
}

function ddmmyyyyToIso(input: string): string | null {
  const match = input.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const [, dd, mm, yyyy] = match;
  const day = Number(dd);
  const month = Number(mm);
  const year = Number(yyyy);
  if (month < 1 || month > 12 || day < 1 || day > 31 || year < 1900 || year > 2100) {
    return null;
  }
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return `${yyyy}-${mm}-${dd}`;
}

function formatAsTyped(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
}

function isoToDate(iso: string): Date | undefined {
  if (!iso) return undefined;
  const parts = iso.split("-");
  if (parts.length !== 3) return undefined;
  return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
}

function dateToIso(date: Date): string {
  const y = date.getFullYear();
  const m = (date.getMonth() + 1).toString().padStart(2, "0");
  const d = date.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function DatePicker({
  label,
  value,
  onChange,
  disabled,
  error,
  helperText,
  id,
  min,
  max,
}: DatePickerProps) {
  const [text, setText] = useState(isoToDDMMYYYY(value));
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

  useEffect(() => {
    setText(isoToDDMMYYYY(value));
  }, [value]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  function handleTextChange(raw: string) {
    const formatted = formatAsTyped(raw);
    setText(formatted);
    const iso = ddmmyyyyToIso(formatted);
    if (iso !== null) {
      onChange(iso);
    }
  }

  function handleBlur() {
    const iso = ddmmyyyyToIso(text);
    if (iso === null && text !== "") {
      setText(isoToDDMMYYYY(value));
    }
  }

  function handleDaySelect(day: Date | undefined) {
    if (!day) return;
    const iso = dateToIso(day);
    onChange(iso);
    setOpen(false);
  }

  const minDate = min ? isoToDate(min) : undefined;
  const maxDate = max ? isoToDate(max) : undefined;
  const selectedDate = isoToDate(value);

  return (
    <div className="w-full" ref={wrapperRef}>
      {label ? (
        <label
          htmlFor={inputId}
          className="block text-sm font-medium text-slate-700 mb-1"
        >
          {label}
        </label>
      ) : null}
      <div className="relative">
        <input
          id={inputId}
          type="text"
          inputMode="numeric"
          placeholder="DD/MM/AAAA"
          value={text}
          onChange={(e) => handleTextChange(e.target.value)}
          onBlur={handleBlur}
          disabled={disabled}
          className={`
            w-full pl-3 pr-10 py-2 rounded-md border text-sm
            focus:outline-none focus:ring-2 focus:ring-offset-0
            disabled:bg-slate-100 disabled:cursor-not-allowed
            ${
              error
                ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                : "border-slate-300 focus:ring-green-500 focus:border-green-500"
            }
          `}
        />
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={disabled}
          tabIndex={-1}
          aria-label="Abrir calendario"
          className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 focus:outline-none disabled:cursor-not-allowed"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </button>
        {open ? (
          <div className="absolute z-50 mt-1 rounded-md border border-slate-200 bg-white shadow-lg p-2">
            <DayPicker
              mode="single"
              selected={selectedDate}
              onSelect={handleDaySelect}
              locale={es}
              disabled={
                minDate || maxDate
                  ? [
                      ...(minDate ? [{ before: minDate }] : []),
                      ...(maxDate ? [{ after: maxDate }] : []),
                    ]
                  : undefined
              }
              showOutsideDays
            />
          </div>
        ) : null}
      </div>
      {error ? (
        <p className="mt-1 text-xs text-red-600">{error}</p>
      ) : helperText ? (
        <p className="mt-1 text-xs text-slate-500">{helperText}</p>
      ) : null}
    </div>
  );
}
