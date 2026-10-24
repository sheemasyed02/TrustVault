import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { ReactNode } from "react";

type BadgeTone = "neutral" | "accent" | "success" | "danger" | "warning";

const toneClass: Record<BadgeTone, string> = {
  neutral: "border border-border bg-surface text-muted",
  accent: "border border-accent/25 bg-accent-soft text-accent-strong",
  success:
    "border border-success/25 bg-[color-mix(in_srgb,var(--success)_12%,white)] text-success",
  danger:
    "border border-danger/25 bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-danger",
  warning:
    "border border-warning/30 bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-warning",
};

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}

export function Badge({ children, tone = "neutral", className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold tracking-wide ${toneClass[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Outcome labels include text + icon so status is not color-only. */
export function OutcomeBadge({ outcome }: { outcome: string }) {
  const upper = outcome.toUpperCase();
  if (upper === "DENIED" || upper === "FAILURE" || upper === "FAILED") {
    return (
      <Badge tone="danger">
        <XCircle className="h-3 w-3" strokeWidth={2} aria-hidden />
        {formatOutcome(upper)}
      </Badge>
    );
  }
  if (upper === "SUCCESS") {
    return (
      <Badge tone="success">
        <CheckCircle2 className="h-3 w-3" strokeWidth={2} aria-hidden />
        Success
      </Badge>
    );
  }
  if (upper === "WARNING") {
    return (
      <Badge tone="warning">
        <AlertTriangle className="h-3 w-3" strokeWidth={2} aria-hidden />
        Warning
      </Badge>
    );
  }
  return <Badge tone="neutral">{formatOutcome(upper)}</Badge>;
}

function formatOutcome(outcome: string): string {
  if (outcome === "DENIED") return "Denied";
  if (outcome === "FAILURE" || outcome === "FAILED") return "Failed";
  if (outcome === "SUCCESS") return "Success";
  return outcome.charAt(0) + outcome.slice(1).toLowerCase();
}
