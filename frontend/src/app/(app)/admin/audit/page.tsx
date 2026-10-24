"use client";

import { RefreshCw, ScrollText } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { AuditEventsTable } from "@/components/audit-events-table";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
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
    return { success, denied, shown: events.length };
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

      <PageHeader
        title="Audit logs"
        description={
          <>
            Persisted security events. Timestamps use your local timezone. For
            hash-chain checks, open{" "}
            <Link
              href="/admin/audit/integrity"
              className="font-semibold text-accent-strong underline"
            >
              Audit Integrity
            </Link>
            .
          </>
        }
        actions={
          <Button
            type="button"
            variant="secondary"
            onClick={() => void load(page, applied)}
          >
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            Refresh
          </Button>
        }
      />

      {status === "ready" ? (
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Matching events" value={String(total)} />
          <StatCard label="On this page" value={String(pageMetrics.shown)} />
          <StatCard label="Success (page)" value={String(pageMetrics.success)} />
          <StatCard label="Denied (page)" value={String(pageMetrics.denied)} />
        </dl>
      ) : null}

      <form
        onSubmit={onApplyFilters}
        className="grid gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-sm)] sm:grid-cols-2 lg:grid-cols-3 sm:p-5"
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
          <span className="tv-label">Outcome</span>
          <select
            value={filters.outcome}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                outcome: e.target.value as FilterState["outcome"],
              }))
            }
            className="tv-input"
          >
            <option value="">Any</option>
            <option value="SUCCESS">Success</option>
            <option value="DENIED">Denied</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="tv-label">From (local)</span>
          <input
            type="datetime-local"
            value={filters.created_from}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, created_from: e.target.value }))
            }
            className="tv-input"
          />
        </label>
        <label className="text-sm">
          <span className="tv-label">To (local)</span>
          <input
            type="datetime-local"
            value={filters.created_to}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, created_to: e.target.value }))
            }
            className="tv-input"
          />
        </label>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3">
          <Button type="submit" variant="primary">
            Apply filters
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setFilters(emptyFilters);
              setApplied(emptyFilters);
            }}
          >
            Clear
          </Button>
        </div>
      </form>

      {status === "loading" ? (
        <div className="space-y-2" role="status" aria-busy>
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full rounded-[0.75rem]" />
          ))}
          <span className="sr-only">Loading audit events...</span>
        </div>
      ) : null}

      {status === "error" ? (
        <Alert
          tone="error"
          action={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void load(page, applied)}
            >
              Retry
            </Button>
          }
        >
          {error ?? "Unable to load audit events."}
        </Alert>
      ) : null}

      {status === "ready" ? <AuditEventsTable events={events} /> : null}

      {status === "ready" && totalPages > 1 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius)] border border-border bg-surface px-4 py-3 text-sm shadow-[var(--shadow-sm)]">
          <p className="text-muted">
            Page {page} of {totalPages} · {total} events
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={page <= 1}
              onClick={() => void load(page - 1, applied)}
            >
              Previous
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => void load(page + 1, applied)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}

      {status === "ready" && totalPages <= 1 && events.length > 0 ? (
        <p className="flex items-center gap-2 text-xs text-muted">
          <ScrollText className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          Showing {events.length} of {total} matching events
        </p>
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
      <span className="tv-label">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="tv-input"
        placeholder={placeholder}
      />
    </label>
  );
}
