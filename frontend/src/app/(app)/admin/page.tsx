"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  getAdminSummaryRequest,
  listAuditEventsRequest,
  verifyAuditIntegrityRequest,
  type AdminSummaryResponse,
  type AuditEventItem,
  type AuditIntegrityResult,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function AdminDashboardPage() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [summary, setSummary] = useState<AdminSummaryResponse | null>(null);
  const [recent, setRecent] = useState<AuditEventItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [integrity, setIntegrity] = useState<AuditIntegrityResult | null>(null);
  const [integrityAt, setIntegrityAt] = useState<string | null>(null);
  const [integrityError, setIntegrityError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
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
  }, [accessToken, handleUnauthorized]);

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [accessToken, load]);

  async function onVerify() {
    if (!accessToken || verifying) return;
    setVerifying(true);
    setIntegrityError(null);
    try {
      const result = await verifyAuditIntegrityRequest(accessToken);
      setIntegrity(result);
      setIntegrityAt(new Date().toISOString());
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setIntegrity(null);
      setIntegrityError(
        err instanceof ApiError
          ? err.detail
          : "Integrity verification request failed.",
      );
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
            Administration
          </p>
          <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
            Admin dashboard
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Counts and audit events come from the live API. Administrator role
            does not grant access to document file contents.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-border px-3 py-2 text-sm font-semibold text-foreground hover:bg-accent-soft"
        >
          Refresh
        </button>
      </header>

      <div className="flex flex-wrap gap-3 text-sm">
        <Link
          href="/admin/users"
          className="font-semibold text-accent-strong hover:underline"
        >
          Manage users
        </Link>
        <span className="text-border">·</span>
        <Link
          href="/admin/audit"
          className="font-semibold text-accent-strong hover:underline"
        >
          Full audit log
        </Link>
      </div>

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading administrator summary…
        </p>
      ) : null}

      {status === "error" ? (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-4 text-sm text-danger"
        >
          <p>{error}</p>
          <button
            type="button"
            className="mt-3 font-semibold underline"
            onClick={() => void load()}
          >
            Retry
          </button>
        </div>
      ) : null}

      {status === "ready" && summary ? (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Stat label="Total users" value={String(summary.users_total)} />
          <Stat label="Active users" value={String(summary.users_active)} />
          <Stat label="Inactive users" value={String(summary.users_inactive)} />
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

      <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl text-foreground">
              Audit chain integrity
            </h2>
            <p className="mt-1 text-sm text-muted">
              Runs server-side hash recalculation. A successful HTTP response is
              not enough — trust the{" "}
              <code className="text-xs">valid</code> field from the API.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void onVerify()}
            disabled={verifying}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
          >
            {verifying ? "Verifying…" : "Verify chain"}
          </button>
        </div>
        {integrityError ? (
          <p role="alert" className="mt-3 text-sm text-danger">
            {integrityError}
          </p>
        ) : null}
        {integrity ? (
          <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">
                Result
              </dt>
              <dd
                className={
                  integrity.valid
                    ? "font-semibold text-accent-strong"
                    : "font-semibold text-danger"
                }
              >
                {integrity.valid ? "Valid" : "Invalid"}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">
                Checked at (local)
              </dt>
              <dd>{integrityAt ? formatDateTime(integrityAt) : "—"}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">
                Events checked
              </dt>
              <dd>
                {integrity.checked_count} / {integrity.event_count}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">
                Reason
              </dt>
              <dd>{integrity.reason_code ?? "—"}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-muted">
                Detail
              </dt>
              <dd className="break-words text-foreground">{integrity.detail}</dd>
            </div>
          </dl>
        ) : (
          <p className="mt-3 text-sm text-muted">
            No verification run yet in this session.
          </p>
        )}
      </section>

      <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
        <h2 className="font-display text-xl text-foreground">
          Recent audit events
        </h2>
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
                <div>
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
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-4 shadow-[var(--shadow)]">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 font-display text-3xl text-foreground">{value}</p>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const denied = outcome === "DENIED";
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
        denied
          ? "bg-danger/10 text-danger"
          : "bg-accent-soft text-accent-strong"
      }`}
    >
      {outcome}
    </span>
  );
}
