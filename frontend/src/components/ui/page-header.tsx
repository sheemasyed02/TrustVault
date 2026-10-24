import type { ReactNode } from "react";

interface PageHeaderProps {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /**
   * Prefer Merienda for page titles (default). Set false for dense data screens
   * where a display face hurts scanability.
   */
  accentTitle?: boolean;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  accentTitle = true,
}: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 max-w-2xl">
        {eyebrow ? (
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent-strong">
            {eyebrow}
          </p>
        ) : null}
        <h1
          className={`mt-1.5 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl ${
            accentTitle ? "font-accent" : "font-sans"
          }`}
        >
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

interface SectionHeadingProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export function SectionHeading({
  title,
  description,
  actions,
}: SectionHeadingProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <h2 className="font-accent text-lg font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        {description ? (
          <div className="mt-1 text-sm text-muted">{description}</div>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
