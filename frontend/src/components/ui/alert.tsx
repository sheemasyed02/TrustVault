import type { ReactNode } from "react";

type AlertTone = "error" | "success" | "info";

interface AlertProps {
  children: ReactNode;
  tone?: AlertTone;
  title?: string;
  action?: ReactNode;
}

const toneClass: Record<AlertTone, string> = {
  error: "border-danger/30 bg-danger/5 text-danger",
  success: "border-accent/30 bg-accent-soft/60 text-accent-strong",
  info: "border-border bg-white/70 text-foreground",
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
      className={`rounded-xl border px-4 py-3 text-sm ${toneClass[tone]}`}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? "mt-1" : ""}>{children}</div>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
