import { useState, useRef, useEffect, useMemo } from "react";

export interface ComboboxOption {
  value: string;
  label: string;
}

interface ComboboxProps {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyLabel?: string;
  className?: string;
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder = "Seleccionar...",
  emptyLabel = "Sin resultados",
  className = "",
}: ComboboxProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightedIdx, setHighlightedIdx] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selected = useMemo(
    () => options.find((o) => o.value === value) ?? null,
    [options, value],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (isOpen) {
      setHighlightedIdx(0);
      inputRef.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    setHighlightedIdx(0);
  }, [query]);

  useEffect(() => {
    if (!isOpen || !listRef.current) return;
    const el = listRef.current.children[highlightedIdx] as
      | HTMLElement
      | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightedIdx, isOpen]);

  function commitSelection(option: ComboboxOption) {
    onChange(option.value);
    setIsOpen(false);
    setQuery("");
  }

  function handleClear(e: React.MouseEvent | React.KeyboardEvent) {
    e.stopPropagation();
    onChange("");
    setQuery("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIdx((idx) => Math.min(idx + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIdx((idx) => Math.max(idx - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const option = filtered[highlightedIdx];
      if (option) commitSelection(option);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
      setQuery("");
    }
  }

  const displayLabel = selected?.label ?? "";
  const hasValue = !!selected;

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="
          w-full flex items-center justify-between gap-2
          px-3 py-2 rounded-md border border-slate-300 bg-white
          text-sm text-left
          focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent
          hover:border-slate-400 transition-colors
        "
      >
        <span
          className={`truncate ${hasValue ? "text-slate-900" : "text-slate-400"}`}
        >
          {displayLabel || placeholder}
        </span>
        <span className="flex items-center gap-1 flex-shrink-0">
          {hasValue ? (
            <span
              role="button"
              tabIndex={0}
              onClick={handleClear}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleClear(e);
                }
              }}
              className="p-0.5 rounded hover:bg-slate-100 cursor-pointer"
              aria-label="Limpiar selección"
            >
              <svg
                className="w-4 h-4 text-slate-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </span>
          ) : null}
          <svg
            className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </span>
      </button>

      {isOpen ? (
        <div
          className="
            absolute z-50 mt-2 left-0 right-0
            bg-white rounded-md border border-slate-200 shadow-lg
            flex flex-col
          "
        >
          <div className="p-2 border-b border-slate-100">
            <div className="relative">
              <svg
                className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Buscar..."
                className="
                  w-full pl-8 pr-2 py-1.5 rounded border border-slate-200
                  text-sm
                  focus:outline-none focus:ring-1 focus:ring-green-500 focus:border-green-500
                "
              />
            </div>
          </div>
          {filtered.length === 0 ? (
            <div className="px-3 py-4 text-sm text-slate-500 text-center">
              {emptyLabel}
            </div>
          ) : (
            <ul ref={listRef} className="max-h-60 overflow-y-auto py-1">
              {filtered.map((option, idx) => {
                const isSelected = option.value === value;
                const isHighlighted = idx === highlightedIdx;
                return (
                  <li key={option.value}>
                    <button
                      type="button"
                      onClick={() => commitSelection(option)}
                      onMouseEnter={() => setHighlightedIdx(idx)}
                      className={`
                        w-full text-left px-3 py-2 text-sm
                        flex items-center justify-between gap-2
                        ${isHighlighted ? "bg-slate-100" : ""}
                        ${isSelected ? "text-green-700 font-medium" : "text-slate-700"}
                      `}
                    >
                      <span className="truncate">{option.label}</span>
                      {isSelected ? (
                        <svg
                          className="w-4 h-4 text-green-600 flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
