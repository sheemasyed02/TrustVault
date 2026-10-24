import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}

/** Standard content surface — pale border, refined radius, soft shadow. */
export function Panel({
  children,
  className = "",
  padded = true,
}: PanelProps) {
  return (
    <section
      className={`rounded-[var(--radius)] border border-border bg-surface shadow-[var(--shadow-sm)] ${
        padded ? "p-5 sm:p-6" : ""
      } ${className}`}
    >
      {children}
    </section>
  );
}

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  className?: string;
}

/** Compact metric card used on dashboards. Wrap with Link when navigable. */
export function StatCard({
  label,
  value,
  hint,
  icon,
  className = "",
}: StatCardProps) {
  return (
    <Panel
      className={`!p-4 transition-[border-color,box-shadow] duration-[180ms] ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          {label}
        </p>
        {icon ? (
          <span className="text-accent" aria-hidden>
            {icon}
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-3xl font-semibold tracking-tight text-foreground">
        {value}
      </p>
      {hint ? <div className="mt-1 text-xs text-muted">{hint}</div> : null}
    </Panel>
  );
}
