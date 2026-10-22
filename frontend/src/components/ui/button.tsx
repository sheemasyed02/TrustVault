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
    "bg-accent text-white hover:bg-accent-strong focus-visible:text-white active:bg-accent-strong disabled:opacity-60 disabled:text-white",
  secondary:
    "border border-border bg-white text-foreground hover:bg-accent-soft disabled:opacity-60",
  /* Outline destructive — list/row actions (always visible, not hover-reveal) */
  danger:
    "border border-danger/60 bg-danger/5 text-danger hover:bg-danger/10 focus-visible:bg-danger/10 active:bg-danger/15 disabled:opacity-60",
  /* Solid destructive — confirmation dialogs; white label on filled danger */
  dangerSolid:
    "border border-transparent bg-danger text-white hover:bg-danger/90 focus-visible:text-white active:bg-danger/90 disabled:opacity-60 disabled:text-white",
  ghost:
    "text-accent-strong hover:bg-accent-soft disabled:opacity-60",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "min-h-8 px-2.5 py-1.5 text-xs leading-none",
  md: "min-h-9 px-3.5 py-2 text-sm leading-none",
};

const baseClass =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

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
