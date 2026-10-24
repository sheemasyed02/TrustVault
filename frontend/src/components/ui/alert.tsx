import type { ReactNode } from "react";

type AlertTone = "error" | "success" | "info" | "warning";

interface AlertProps {
  children: ReactNode;
  tone?: AlertTone;
  title?: string;
  action?: ReactNode;
}

const toneClass: Record<AlertTone, string> = {
  error:
    "border-danger/30 bg-[color-mix(in_srgb,var(--danger)_8%,white)] text-danger",
  success:
    "border-success/30 bg-[color-mix(in_srgb,var(--success)_10%,white)] text-success",
  warning:
    "border-warning/30 bg-[color-mix(in_srgb,var(--warning)_10%,white)] text-warning",
  info: "border-border bg-accent-soft/60 text-foreground",
};

export function Alert({
  children,
  tone = "info",
  title,
  action,
}: AlertProps) {
  const role = tone === "error" ? "alert" : "status";
  return (
    <div
      role={role}
      className={`rounded-[var(--radius)] border px-4 py-3 text-sm ${toneClass[tone]}`}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? "mt-1" : ""}>{children}</div>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
