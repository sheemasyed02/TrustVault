"use client";

import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

interface AuthTextFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  id?: string;
  label: string;
  leadingIcon?: ReactNode;
  invalid?: boolean;
  hint?: string;
}

/**
 * Auth text input with optional leading icon.
 * Left padding is reserved so icons never cover placeholder or value text.
 */
export function AuthTextField({
  id,
  label,
  leadingIcon,
  invalid = false,
  hint,
  disabled,
  className = "",
  ...rest
}: AuthTextFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = `${fieldId}-hint`;

  return (
    <div>
      <label htmlFor={fieldId} className="tv-label">
        {label}
      </label>
      <div className="relative">
        {leadingIcon ? (
          <span className="tv-input-icon-slot tv-input-icon-slot--leading" aria-hidden>
            {leadingIcon}
          </span>
        ) : null}
        <input
          id={fieldId}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-describedby={hint ? hintId : undefined}
          className={`tv-input ${leadingIcon ? "tv-input-with-leading-icon" : ""} ${
            invalid ? "border-danger focus:border-danger" : ""
          } ${className}`.trim()}
          {...rest}
        />
      </div>
      {hint ? (
        <p id={hintId} className="mt-1.5 text-xs text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
