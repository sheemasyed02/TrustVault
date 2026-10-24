import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: EmptyStateProps) {
  return (
    <div
      className="rounded-[var(--radius)] border border-dashed border-border bg-accent-soft/40 px-6 py-12 text-center"
      role="status"
    >
      {icon ? (
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-surface text-accent shadow-[var(--shadow-sm)]">
          {icon}
        </div>
      ) : null}
      <p className="font-semibold text-foreground">{title}</p>
      {description ? (
        <div className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">
          {description}
        </div>
      ) : null}
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </div>
  );
}
