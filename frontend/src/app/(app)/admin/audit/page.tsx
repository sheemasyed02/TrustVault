"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listAuditEventsRequest,
  verifyAuditIntegrityRequest,
  type AuditEventItem,
  type AuditIntegrityResult,
  type AuditListParams,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

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

function displayUser(
  id: string | null,
  name?: string | null,
  email?: string | null,
): string {
  if (email) return name ? `${name} <${email}>` : email;
  return id ?? "—";
}

export default function AdminAuditPage() {
  return (
    <Suspense
      fallback={
        <p className="text-sm text-muted" role="status">
          Loading audit log…
        </p>
      }
    >
      <AdminAuditPageContent />
    </Suspense>
  );
}

function AdminAuditPageContent() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const searchParams = useSearchParams();
  const integritySectionRef = useRef<HTMLElement | null>(null);
  const [filters, setFilters] = useState<FilterState>(emptyFilters);
  const [applied, setApplied] = useState<FilterState>(emptyFilters);
  const [page, setPage] = useState(1);
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [integrity, setIntegrity] = useState<AuditIntegrityResult | null>(null);
  const [integrityAt, setIntegrityAt] = useState<string | null>(null);
  const [integrityError, setIntegrityError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

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

  useEffect(() => {
    if (searchParams.get("focus") !== "integrity") return;
    integritySectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [searchParams]);

  function onApplyFilters(event: FormEvent) {
    event.preventDefault();
    setApplied({ ...filters });
  }

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
    <div className="space-y-5">
      <Link
        href="/admin"
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← Admin dashboard
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl tracking-tight text-foreground">
            Audit log
          </h1>
          <p className="mt-2 text-sm text-muted">
            Platform-wide metadata only — never confidential document contents.
            Timestamps are shown in your local timezone; the API stores UTC.
            Hash-chain integrity detects many in-place edits but is not
            tamper-proof against a privileged database administrator who can
            rewrite the whole table.
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

      <section
        ref={integritySectionRef}
        id="audit-integrity"
        className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl text-foreground">
              Audit chain integrity
            </h2>
            <p className="mt-1 text-sm text-muted">
              A green valid badge is shown only when the API returns{" "}
              <code className="text-xs">valid: true</code>.
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
        <div
          className={`mt-3 rounded-xl border px-4 py-3 text-sm ${
            integrity.valid
              ? "border-accent/30 bg-accent-soft/40 text-foreground"
              : "border-danger/30 bg-danger/5 text-danger"
          }`}
          role="status"
        >
          <p className="font-semibold">
            Chain {integrity.valid ? "valid" : "invalid"}
            {integrityAt ? ` · checked ${formatDateTime(integrityAt)}` : ""}
          </p>
          <p className="mt-1">
            {integrity.detail}
            {integrity.reason_code ? ` (${integrity.reason_code})` : ""}
          </p>
          <p className="mt-1 text-xs text-muted">
            Checked {integrity.checked_count} of {integrity.event_count} events
            {integrity.first_failure_event_id
              ? ` · first failure ${integrity.first_failure_event_id}`
              : ""}
          </p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted">
          No verification run yet in this session.
        </p>
      )}
      </section>

      <form
        onSubmit={onApplyFilters}
        className="grid gap-3 rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)] sm:grid-cols-2 lg:grid-cols-3"
      >
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            Actor ID
          </span>
          <input
            value={filters.actor_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, actor_id: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
            placeholder="UUID"
          />
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            Action
          </span>
          <input
            value={filters.action}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, action: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
            placeholder="LOGIN"
          />
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            Document ID
          </span>
          <input
            value={filters.document_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, document_id: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
            placeholder="UUID"
          />
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            Owner ID
          </span>
          <input
            value={filters.owner_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, owner_id: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
            placeholder="Document owner UUID"
          />
        </label>
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
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
          >
            <option value="">Any</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="DENIED">DENIED</option>
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
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
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
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
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
        <div role="alert" className="text-sm text-danger">
          <p>{error}</p>
          <button
            type="button"
            className="mt-2 font-semibold underline"
            onClick={() => void load(page, applied)}
          >
            Retry
          </button>
        </div>
      ) : null}
      {status === "ready" && events.length === 0 ? (
        <p className="text-sm text-muted" role="status">
          No audit events match these filters.
        </p>
      ) : null}

      {status === "ready" && events.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-3 font-semibold">When</th>
                <th className="px-3 py-3 font-semibold">Action</th>
                <th className="px-3 py-3 font-semibold">Outcome</th>
                <th className="px-3 py-3 font-semibold">Actor</th>
                <th className="px-3 py-3 font-semibold">Target</th>
                <th className="px-3 py-3 font-semibold">Document</th>
                <th className="px-3 py-3 font-semibold">Reason</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id} className="border-b border-border/70 align-top">
                  <td className="px-3 py-3 text-muted">
                    {formatDateTime(event.created_at)}
                  </td>
                  <td className="px-3 py-3 font-medium text-foreground">
                    {event.action}
                    {typeof event.metadata?.permission === "string" ? (
                      <span className="mt-0.5 block text-xs font-normal text-muted">
                        {event.metadata.permission}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
                        event.outcome === "DENIED"
                          ? "bg-danger/10 text-danger"
                          : "bg-accent-soft text-accent-strong"
                      }`}
                    >
                      {event.outcome}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted">
                    {displayUser(
                      event.actor_id,
                      event.actor_name,
                      event.actor_email,
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs text-muted">
                    {displayUser(
                      event.target_user_id,
                      event.target_user_name,
                      event.target_user_email,
                    )}
                  </td>
                  <td className="px-3 py-3 break-all font-mono text-[11px] text-muted">
                    {event.document_id ?? "—"}
                  </td>
                  <td className="px-3 py-3 text-muted">
                    {event.reason_code ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

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
            Page {page} of {totalPages} ({total} events)
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
