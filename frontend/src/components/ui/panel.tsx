import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}

/** Standard content surface — border, radius, soft shadow. */
export function Panel({
  children,
  className = "",
  padded = true,
}: PanelProps) {
  return (
    <section
      className={`rounded-xl border border-border bg-surface shadow-[var(--shadow-sm)] ${
        padded ? "p-5 sm:p-6" : ""
      } ${className}`}
    >
      {children}
    </section>
  );
}
