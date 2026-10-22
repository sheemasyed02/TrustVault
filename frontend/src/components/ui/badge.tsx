import type { ReactNode } from "react";

type BadgeTone = "neutral" | "accent" | "success" | "danger" | "warning";

const toneClass: Record<BadgeTone, string> = {
  neutral: "border border-border bg-white text-muted",
  accent: "border border-accent/20 bg-accent-soft text-accent-strong",
  success: "border border-accent/20 bg-accent-soft text-accent-strong",
  danger: "border border-danger/25 bg-danger/5 text-danger",
  warning: "border border-border bg-white text-foreground",
};

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}

export function Badge({ children, tone = "neutral", className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold ${toneClass[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Outcome labels include text so status is not color-only. */
export function OutcomeBadge({ outcome }: { outcome: string }) {
  const upper = outcome.toUpperCase();
  if (upper === "DENIED" || upper === "FAILURE" || upper === "FAILED") {
    return <Badge tone="danger">{formatOutcome(upper)}</Badge>;
  }
  if (upper === "SUCCESS") {
    return <Badge tone="success">Success</Badge>;
  }
  return <Badge tone="neutral">{formatOutcome(upper)}</Badge>;
}

function formatOutcome(outcome: string): string {
  if (outcome === "DENIED") return "Denied";
  if (outcome === "FAILURE" || outcome === "FAILED") return "Failed";
  if (outcome === "SUCCESS") return "Success";
  return outcome.charAt(0) + outcome.slice(1).toLowerCase();
}
