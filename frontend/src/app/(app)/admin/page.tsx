"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { OutcomeBadge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import {
  ApiError,
  getAdminSummaryRequest,
  listAuditEventsRequest,
  type AdminSummaryResponse,
  type AuditEventItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

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
        eyebrow="Administration"
        title="Admin dashboard"
        description="User and audit totals from the live API. Opening documents still requires ownership or an explicit grant."
        actions={
          <Button variant="secondary" onClick={() => void load()}>
            Refresh
          </Button>
        }
      />

      <nav className="flex flex-wrap gap-x-4 gap-y-2 text-sm" aria-label="Admin shortcuts">
        <Link
          href="/admin/users"
          className="font-semibold text-accent-strong hover:underline"
        >
          Manage Users
        </Link>
        <Link
          href="/admin/audit"
          className="font-semibold text-accent-strong hover:underline"
        >
          Audit Logs
        </Link>
        <Link
          href="/admin/audit/integrity"
          className="font-semibold text-accent-strong hover:underline"
        >
          Audit Integrity
        </Link>
        <Link
          href="/profile"
          className="font-semibold text-accent-strong hover:underline"
        >
          Profile
        </Link>
      </nav>

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading summary…
        </p>
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
          <Stat label="Users" value={String(summary.users_total)} />
          <Stat label="Active" value={String(summary.users_active)} />
          <Stat label="Inactive" value={String(summary.users_inactive)} />
          <Stat
            label="Audit successes"
            value={String(summary.audit_success_total)}
          />
          <Stat
            label="Audit denials"
            value={String(summary.audit_denied_total)}
          />
        </section>
      ) : null}

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl text-foreground">
            Recent audit events
          </h2>
          <Link
            href="/admin/audit"
            className="text-sm font-semibold text-accent-strong hover:underline"
          >
            View all logs
          </Link>
        </div>
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
                  <p className="font-semibold text-foreground">{event.action}</p>
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Panel className="!p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 font-display text-3xl text-foreground">{value}</p>
    </Panel>
  );
}
