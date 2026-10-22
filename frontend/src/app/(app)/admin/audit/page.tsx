"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { AuditEventsTable } from "@/components/audit-events-table";
import {
  ApiError,
  listAuditEventsRequest,
  type AuditEventItem,
  type AuditListParams,
} from "@/lib/api";

interface FilterState {
  actor_id: string;
  action: string;
  document_id: string;
  owner_id: string;
  outcome: "" | "SUCCESS" | "DENIED";
  created_from: string;
  created_to: string;
}

const emptyFilters: FilterState = {
  actor_id: "",
  action: "",
  document_id: "",
  owner_id: "",
  outcome: "",
  created_from: "",
  created_to: "",
};

/**
 * Admin Audit Logs — answers "what happened?"
 * Integrity verification lives on /admin/audit/integrity.
 */
export default function AdminAuditLogsPage() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [filters, setFilters] = useState<FilterState>(emptyFilters);
  const [applied, setApplied] = useState<FilterState>(emptyFilters);
  const [page, setPage] = useState(1);
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (nextPage: number, nextFilters: FilterState, signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      const params: AuditListParams = {
        page: nextPage,
        page_size: 20,
        actor_id: nextFilters.actor_id.trim() || undefined,
        action: nextFilters.action.trim() || undefined,
        document_id: nextFilters.document_id.trim() || undefined,
        owner_id: nextFilters.owner_id.trim() || undefined,
        outcome: nextFilters.outcome || undefined,
        created_from: nextFilters.created_from
          ? new Date(nextFilters.created_from).toISOString()
          : undefined,
        created_to: nextFilters.created_to
          ? new Date(nextFilters.created_to).toISOString()
          : undefined,
      };
      try {
        const data = await listAuditEventsRequest(accessToken, params, signal);
        setEvents(data.results);
        setPage(data.page);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setEvents([]);
        setError(
          err instanceof ApiError ? err.detail : "Unable to load audit events.",
        );
        setStatus("error");
      }
    },
    [accessToken, handleUnauthorized],
  );

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void load(1, applied, controller.signal);
    return () => controller.abort();
  }, [accessToken, applied, load]);

  const pageMetrics = useMemo(() => {
    const success = events.filter((e) => e.outcome === "SUCCESS").length;
    const denied = events.filter((e) => e.outcome === "DENIED").length;
    const views = events.filter((e) => e.action === "DOCUMENT_VIEW").length;
    return { success, denied, views, shown: events.length };
  }, [events]);

  function onApplyFilters(event: FormEvent) {
    event.preventDefault();
    setApplied({ ...filters });
  }

  return (
    <div className="space-y-5">
      <Link
        href="/admin"
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← Admin dashboard
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
            Administration
          </p>
          <h1 className="mt-2 font-display text-2xl tracking-tight text-foreground sm:text-3xl">
            Audit logs
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted">
            Persisted security events across the platform. Timestamps use your
            local timezone. For hash-chain checks, open{" "}
            <Link
              href="/admin/audit/integrity"
              className="font-semibold text-accent-strong underline"
            >
              Audit Integrity
            </Link>
            .
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load(page, applied)}
          className="rounded-md border border-border px-3 py-2 text-sm font-semibold hover:bg-accent-soft"
        >
          Refresh
        </button>
      </header>

      {status === "ready" ? (
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Matching events" value={String(total)} />
          <Metric label="On this page" value={String(pageMetrics.shown)} />
          <Metric label="Success (page)" value={String(pageMetrics.success)} />
          <Metric label="Denied (page)" value={String(pageMetrics.denied)} />
        </dl>
      ) : null}

      <form
        onSubmit={onApplyFilters}
        className="grid gap-3 rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)] sm:grid-cols-2 lg:grid-cols-3"
      >
        <Field
          label="Actor ID"
          value={filters.actor_id}
          onChange={(v) => setFilters((p) => ({ ...p, actor_id: v }))}
          placeholder="UUID"
        />
        <Field
          label="Action"
          value={filters.action}
          onChange={(v) => setFilters((p) => ({ ...p, action: v }))}
          placeholder="DOCUMENT_VIEW"
        />
        <Field
          label="Document ID"
          value={filters.document_id}
          onChange={(v) => setFilters((p) => ({ ...p, document_id: v }))}
          placeholder="UUID"
        />
        <Field
          label="Owner ID"
          value={filters.owner_id}
          onChange={(v) => setFilters((p) => ({ ...p, owner_id: v }))}
          placeholder="Document owner UUID"
        />
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            Outcome
          </span>
          <select
            value={filters.outcome}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                outcome: e.target.value as FilterState["outcome"],
              }))
            }
            className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
          >
            <option value="">Any</option>
            <option value="SUCCESS">Success</option>
            <option value="DENIED">Denied</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            From (local)
          </span>
          <input
            type="datetime-local"
            value={filters.created_from}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, created_from: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
          />
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            To (local)
          </span>
          <input
            type="datetime-local"
            value={filters.created_to}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, created_to: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
          />
        </label>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3">
          <button
            type="submit"
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong"
          >
            Apply filters
          </button>
          <button
            type="button"
            onClick={() => {
              setFilters(emptyFilters);
              setApplied(emptyFilters);
            }}
            className="rounded-md border border-border px-4 py-2 text-sm font-semibold hover:bg-accent-soft"
          >
            Clear
          </button>
        </div>
      </form>

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading audit events…
        </p>
      ) : null}

      {status === "error" ? (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm"
        >
          <p className="text-danger">{error}</p>
          <button
            type="button"
            className="mt-2 font-semibold text-danger underline"
            onClick={() => void load(page, applied)}
          >
            Retry
          </button>
        </div>
      ) : null}

      {status === "ready" ? <AuditEventsTable events={events} /> : null}

      {status === "ready" && totalPages > 1 ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => void load(page - 1, applied)}
            className="rounded-md border border-border px-3 py-1.5 font-semibold disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-muted">
            Page {page} of {totalPages} · {total} events
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => void load(page + 1, applied)}
            className="rounded-md border border-border px-3 py-1.5 font-semibold disabled:opacity-50"
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="text-sm">
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
        placeholder={placeholder}
      />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3 shadow-[var(--shadow)]">
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 font-display text-2xl text-foreground">{value}</dd>
    </div>
  );
}
