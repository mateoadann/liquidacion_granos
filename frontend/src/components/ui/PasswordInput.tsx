import { type InputHTMLAttributes, forwardRef, useState } from "react";

interface PasswordInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ label, error, helperText, className = "", id, ...props }, ref) => {
    const [visible, setVisible] = useState(false);
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="w-full">
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
            ref={ref}
            id={inputId}
            type={visible ? "text" : "password"}
            className={`
              w-full pl-3 pr-10 py-2 rounded-md border text-sm
              focus:outline-none focus:ring-2 focus:ring-offset-0
              disabled:bg-slate-100 disabled:cursor-not-allowed
              ${
                error
                  ? "border-red-500 focus:ring-red-500 focus:border-red-500"
                  : "border-slate-300 focus:ring-green-500 focus:border-green-500"
              }
              ${className}
            `}
            {...props}
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            tabIndex={-1}
            aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
            className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 focus:outline-none"
          >
            {visible ? (
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
                />
              </svg>
            ) : (
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                />
              </svg>
            )}
          </button>
        </div>
        {error ? (
          <p className="mt-1 text-xs text-red-600">{error}</p>
        ) : helperText ? (
          <p className="mt-1 text-xs text-slate-500">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

PasswordInput.displayName = "PasswordInput";
