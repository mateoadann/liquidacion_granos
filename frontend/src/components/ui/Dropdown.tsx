import { useState, useRef, useEffect, useLayoutEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface DropdownProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
}

const MENU_WIDTH = 192; // matches w-48
const VIEWPORT_MARGIN = 8;

export function Dropdown({ trigger, children, align = "right" }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(
    null,
  );

  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  function updatePosition() {
    const triggerEl = triggerRef.current;
    const menuEl = menuRef.current;
    if (!triggerEl) return;

    const triggerRect = triggerEl.getBoundingClientRect();
    const menuHeight = menuEl?.offsetHeight ?? 0;

    let left =
      align === "right"
        ? triggerRect.right - MENU_WIDTH
        : triggerRect.left;

    left = Math.max(
      VIEWPORT_MARGIN,
      Math.min(left, window.innerWidth - MENU_WIDTH - VIEWPORT_MARGIN),
    );

    const spaceBelow = window.innerHeight - triggerRect.bottom;
    const openUp = menuHeight > 0 && spaceBelow < menuHeight + VIEWPORT_MARGIN;
    const top = openUp
      ? triggerRect.top - menuHeight - 4
      : triggerRect.bottom + 4;

    setPosition({ top, left });
  }

  useLayoutEffect(() => {
    if (isOpen) updatePosition();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        menuRef.current?.contains(target)
      ) {
        return;
      }
      setIsOpen(false);
    }

    function handleViewportChange() {
      setIsOpen(false);
    }

    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("scroll", handleViewportChange, true);
    window.addEventListener("resize", handleViewportChange);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("scroll", handleViewportChange, true);
      window.removeEventListener("resize", handleViewportChange);
    };
  }, [isOpen]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen((v) => !v);
        }}
        className="p-1 rounded hover:bg-slate-100 transition-colors"
      >
        {trigger}
      </button>

      {isOpen && position
        ? createPortal(
            <div
              ref={menuRef}
              style={{
                position: "fixed",
                top: position.top,
                left: position.left,
                width: MENU_WIDTH,
              }}
              className="z-50 py-1 bg-white rounded-lg border border-slate-200 shadow-lg"
              onClick={(e) => e.stopPropagation()}
            >
              {children}
            </div>,
            document.body,
          )
        : null}
    </>
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
