import type { ReactNode } from "react";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0 max-w-2xl">
        {eyebrow ? (
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent-strong">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="mt-1.5 font-display text-2xl tracking-tight text-foreground sm:text-3xl">
          {title}
        </h1>
        {description ? (
          <div className="mt-2 text-sm leading-6 text-muted">{description}</div>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2 self-center">
          {actions}
        </div>
      ) : null}
    </header>
  );
}
