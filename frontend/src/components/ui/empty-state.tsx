import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div
      className="rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center shadow-[var(--shadow-sm)]"
      role="status"
    >
      <p className="font-medium text-foreground">{title}</p>
      {description ? (
        <div className="mx-auto mt-2 max-w-md text-sm text-muted">
          {description}
        </div>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
