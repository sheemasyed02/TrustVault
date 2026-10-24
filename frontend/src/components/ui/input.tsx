import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: ReactNode;
  error?: string | null;
  leadingIcon?: ReactNode;
}

/** Textured text / search / date / password field with consistent focus states. */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  function Input(
    {
      label,
      hint,
      error,
      leadingIcon,
      id,
      className = "",
      disabled,
      ...rest
    },
    ref,
  ) {
    const describedBy = error
      ? `${id}-error`
      : hint
        ? `${id}-hint`
        : undefined;

    return (
      <div className="w-full">
        {label ? (
          <label htmlFor={id} className="tv-label">
            {label}
          </label>
        ) : null}
        <div className="relative">
          {leadingIcon ? (
            <span
              className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-muted"
              aria-hidden
            >
              {leadingIcon}
            </span>
          ) : null}
          <input
            ref={ref}
            id={id}
            disabled={disabled}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={`tv-input ${leadingIcon ? "pl-9" : ""} ${className}`.trim()}
            {...rest}
          />
        </div>
        {error ? (
          <p id={`${id}-error`} role="alert" className="mt-1.5 text-xs text-danger">
            {error}
          </p>
        ) : hint ? (
          <p id={`${id}-hint`} className="mt-1.5 text-xs text-muted">
            {hint}
          </p>
        ) : null}
      </div>
    );
  },
);

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  function Select(
    { label, hint, error, id, className = "", children, ...rest },
    ref,
  ) {
    return (
      <div className="w-full">
        {label ? (
          <label htmlFor={id} className="tv-label">
            {label}
          </label>
        ) : null}
        <select
          ref={ref}
          id={id}
          aria-invalid={error ? true : undefined}
          className={`tv-input ${className}`.trim()}
          {...rest}
        >
          {children}
        </select>
        {error ? (
          <p role="alert" className="mt-1.5 text-xs text-danger">
            {error}
          </p>
        ) : hint ? (
          <p className="mt-1.5 text-xs text-muted">{hint}</p>
        ) : null}
      </div>
    );
  },
);
