import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "danger"
  | "dangerSolid"
  | "ghost";
export type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

const variantClass: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-white shadow-sm hover:bg-accent-strong focus-visible:text-white active:bg-accent-strong disabled:opacity-60 disabled:text-white",
  secondary:
    "border border-border bg-surface text-foreground hover:bg-accent-soft disabled:opacity-60",
  /* Outline destructive — list/row actions (always visible, not hover-reveal) */
  danger:
    "border border-danger/50 bg-[color-mix(in_srgb,var(--danger)_6%,white)] text-danger hover:bg-[color-mix(in_srgb,var(--danger)_12%,white)] focus-visible:bg-[color-mix(in_srgb,var(--danger)_12%,white)] active:bg-[color-mix(in_srgb,var(--danger)_16%,white)] disabled:opacity-60",
  /* Solid destructive — confirmation dialogs; white label on filled danger */
  dangerSolid:
    "border border-transparent bg-danger text-white hover:bg-[color-mix(in_srgb,var(--danger)_88%,black)] focus-visible:text-white active:bg-[color-mix(in_srgb,var(--danger)_88%,black)] disabled:opacity-60 disabled:text-white",
  ghost:
    "text-accent-strong hover:bg-accent-soft disabled:opacity-60",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "min-h-8 rounded-[0.5rem] px-2.5 py-1.5 text-xs leading-none",
  md: "min-h-9 rounded-[0.625rem] px-3.5 py-2 text-sm leading-none",
};

const baseClass =
  "inline-flex items-center justify-center gap-1.5 font-semibold transition-[background-color,border-color,color,box-shadow,opacity] duration-[180ms] ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

/** Shared class string for `<button>` and Next.js `<Link>` CTAs. */
export function buttonClassName({
  variant = "secondary",
  size = "md",
  className = "",
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
} = {}): string {
  return `${baseClass} ${variantClass[variant]} ${sizeClass[size]} ${className}`.trim();
}

/** Shared action control — keeps primary / secondary / destructive styling consistent. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "secondary",
      size = "md",
      className = "",
      type = "button",
      children,
      ...rest
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        className={buttonClassName({ variant, size, className })}
        {...rest}
      >
        {children}
      </button>
    );
  },
);
