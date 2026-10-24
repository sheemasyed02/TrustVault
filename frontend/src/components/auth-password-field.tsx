"use client";

import { Eye, EyeOff, Lock } from "lucide-react";
import { useId, useState, type InputHTMLAttributes } from "react";

interface AuthPasswordFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "id"> {
  id?: string;
  label: string;
  hint?: string;
  invalid?: boolean;
  /** Show a lock icon inside the left edge of the field (auth screens). */
  showLeadingIcon?: boolean;
}

/** Password field with lock icon and in-field show/hide control. */
export function AuthPasswordField({
  id,
  label,
  hint,
  invalid = false,
  disabled,
  className = "",
  showLeadingIcon = true,
  ...rest
}: AuthPasswordFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = `${fieldId}-hint`;
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <label htmlFor={fieldId} className="tv-label">
        {label}
      </label>
      <div className="relative">
        {showLeadingIcon ? (
          <span className="tv-input-icon-slot tv-input-icon-slot--leading" aria-hidden>
            <Lock className="h-4 w-4" strokeWidth={1.75} />
          </span>
        ) : null}
        <input
          id={fieldId}
          type={visible ? "text" : "password"}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-describedby={hint ? hintId : undefined}
          className={`tv-input ${showLeadingIcon ? "tv-input-with-leading-icon" : ""} tv-input-with-trailing-icon ${
            invalid ? "border-danger focus:border-danger" : ""
          } ${className}`.trim()}
          {...rest}
        />
        <span className="tv-input-icon-slot tv-input-icon-slot--trailing">
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-[0.5rem] text-muted transition-colors duration-[180ms] hover:bg-accent-soft hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
            onClick={() => setVisible((value) => !value)}
            disabled={disabled}
            aria-pressed={visible}
            aria-label={visible ? "Hide password" : "Show password"}
          >
            {visible ? (
              <EyeOff className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            ) : (
              <Eye className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            )}
          </button>
        </span>
      </div>
      {hint ? (
        <p id={hintId} className="mt-1.5 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
