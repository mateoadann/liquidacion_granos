import { useState, useRef, useEffect, type ReactNode } from "react";

interface DropdownProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
}

export function Dropdown({ trigger, children, align = "right" }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={dropdownRef} className="relative inline-block">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className="p-1 rounded hover:bg-slate-100 transition-colors"
      >
        {trigger}
      </button>

      {isOpen ? (
        <div
          className={`
            absolute z-50 mt-1 w-48 py-1
            bg-white rounded-lg border border-slate-200 shadow-lg
            ${align === "right" ? "right-0" : "left-0"}
          `}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

interface DropdownItemProps {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "danger";
  disabled?: boolean;
}

export function DropdownItem({
  children,
  onClick,
  variant = "default",
  disabled = false,
}: DropdownItemProps) {
  const variantClasses = {
    default: "text-slate-700 hover:bg-slate-50",
    danger: "text-red-600 hover:bg-red-50",
  };

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      disabled={disabled}
      className={`
        w-full px-4 py-2 text-sm text-left
        ${variantClasses[variant]}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      {children}
    </button>
  );
}

export function DropdownDivider() {
  return <div className="my-1 border-t border-slate-100" />;
}
