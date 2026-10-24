"use client";

import {
  FileWarning,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  UserCog,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { OutcomeBadge } from "@/components/ui/badge";
import { Button, buttonClassName } from "@/components/ui/button";
import { PageHeader, SectionHeading } from "@/components/ui/page-header";
import { Panel, StatCard } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  getAdminSummaryRequest,
  listAuditEventsRequest,
  type AdminSummaryResponse,
  type AuditEventItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const shortcuts = [
  {
    href: "/admin/users",
    label: "Manage users",
    hint: "Search accounts and status",
    icon: Users,
  },
  {
    href: "/admin/promotions",
    label: "Owner requests",
    hint: "Review Viewer promotions",
    icon: UserCog,
  },
  {
    href: "/admin/audit",
    label: "Audit logs",
    hint: "Security event history",
    icon: ScrollText,
  },
  {
    href: "/admin/audit/integrity",
    label: "Audit integrity",
    hint: "Verify hash-chain checks",
    icon: ShieldCheck,
  },
] as const;

export default function AdminDashboardPage() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [summary, setSummary] = useState<AdminSummaryResponse | null>(null);
  const [recent, setRecent] = useState<AuditEventItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const [summaryData, events] = await Promise.all([
          getAdminSummaryRequest(accessToken, signal),
          listAuditEventsRequest(
            accessToken,
            { page: 1, page_size: 8 },
            signal,
          ),
        ]);
        setSummary(summaryData);
        setRecent(events.results);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setSummary(null);
        setRecent([]);
        setError(
          err instanceof ApiError
            ? err.detail
            : "Unable to load administrator summary.",
        );
        setStatus("error");
      }
    },
    [accessToken, handleUnauthorized],
  );

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [accessToken, load]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Admin dashboard"
        description="Live user and audit totals. Document contents still require ownership or an explicit grant."
        actions={
          <Button variant="secondary" onClick={() => void load()}>
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            Refresh
          </Button>
        }
      />

      <nav
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Admin shortcuts"
      >
        {shortcuts.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-sm)] transition-shadow duration-[180ms] hover:border-accent/40 hover:shadow-[var(--shadow)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
                <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </span>
              <p className="mt-3 text-sm font-semibold text-foreground">
                {item.label}
              </p>
              <p className="mt-0.5 text-xs text-muted">{item.hint}</p>
            </Link>
          );
        })}
      </nav>

      {status === "loading" ? (
        <section
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
          aria-busy
          role="status"
        >
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full rounded-[var(--radius)]" />
          ))}
          <span className="sr-only">Loading summary…</span>
        </section>
      ) : null}

      {status === "error" ? (
        <Alert
          tone="error"
          action={
            <Button size="sm" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {status === "ready" && summary ? (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard
            label="Users"
            value={String(summary.users_total)}
            icon={<Users className="h-4 w-4" strokeWidth={1.75} />}
          />
          <StatCard label="Active" value={String(summary.users_active)} />
          <StatCard label="Inactive" value={String(summary.users_inactive)} />
          <StatCard
            label="Audit successes"
            value={String(summary.audit_success_total)}
            icon={<ShieldCheck className="h-4 w-4" strokeWidth={1.75} />}
          />
          <StatCard
            label="Audit denials"
            value={String(summary.audit_denied_total)}
            icon={<FileWarning className="h-4 w-4" strokeWidth={1.75} />}
          />
        </section>
      ) : null}

      <Panel>
        <SectionHeading
          title="Recent audit events"
          actions={
            <Link
              href="/admin/audit"
              className={buttonClassName({ variant: "ghost", size: "sm" })}
            >
              <ScrollText className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              View all logs
            </Link>
          }
        />
        {status === "loading" ? (
          <div className="mt-4 space-y-2" aria-hidden>
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-[70%]" />
          </div>
        ) : null}
        {status === "ready" && recent.length === 0 ? (
          <p className="mt-3 text-sm text-muted" role="status">
            No audit events yet.
          </p>
        ) : null}
        {recent.length > 0 ? (
          <ul className="mt-4 divide-y divide-border">
            {recent.map((event) => (
              <li
                key={event.id}
                className="flex flex-wrap items-baseline justify-between gap-2 py-3 text-sm"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-foreground">
                    {event.action.replaceAll("_", " ")}
                  </p>
                  <p className="text-xs text-muted">
                    {formatDateTime(event.created_at)}
                    {event.reason_code ? ` · ${event.reason_code}` : ""}
                  </p>
                </div>
                <OutcomeBadge outcome={event.outcome} />
              </li>
            ))}
          </ul>
        ) : null}
      </Panel>
    </div>
  );
}
