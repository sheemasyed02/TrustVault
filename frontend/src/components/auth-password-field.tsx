"use client";

import { Eye, EyeOff } from "lucide-react";
import { useId, useState, type InputHTMLAttributes } from "react";

interface AuthPasswordFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "id"> {
  id?: string;
  label: string;
  hint?: string;
  invalid?: boolean;
}

/** Password field with show/hide control for auth screens. */
export function AuthPasswordField({
  id,
  label,
  hint,
  invalid = false,
  disabled,
  className = "",
  ...rest
}: AuthPasswordFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = `${fieldId}-hint`;
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between gap-2">
        <label htmlFor={fieldId} className="tv-label mb-0">
          {label}
        </label>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-[0.375rem] px-1.5 py-0.5 text-xs font-semibold text-accent-strong transition-colors duration-[180ms] hover:bg-accent-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
          onClick={() => setVisible((value) => !value)}
          disabled={disabled}
          aria-pressed={visible}
          aria-label={visible ? "Hide password" : "Show password"}
        >
          {visible ? (
            <EyeOff className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          ) : (
            <Eye className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          )}
          {visible ? "Hide" : "Show"}
        </button>
      </div>
      <input
        id={fieldId}
        type={visible ? "text" : "password"}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={hint ? hintId : undefined}
        className={`tv-input ${invalid ? "border-danger focus:border-danger" : ""} ${className}`.trim()}
        {...rest}
      />
      {hint ? (
        <p id={hintId} className="mt-1.5 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
