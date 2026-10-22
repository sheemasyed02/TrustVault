"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listAdminDocumentViewsRequest,
  listAuditEventsRequest,
  type AuditEventItem,
  type DocumentViewActivityItem,
  type DocumentViewPlatformSummary,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface FilterState {
  q: string;
  owner_id: string;
  viewer_id: string;
  created_from: string;
  created_to: string;
}

const emptyFilters: FilterState = {
  q: "",
  owner_id: "",
  viewer_id: "",
  created_from: "",
  created_to: "",
};

function viewerLabel(event: AuditEventItem): string {
  const role =
    typeof event.metadata?.actor_role === "string"
      ? event.metadata.actor_role
      : null;
  const email = event.actor_email;
  const name = event.actor_name;
  const who = email
    ? name
      ? `${name} <${email}>`
      : email
    : (event.actor_id ?? "—");
  return role ? `${who} · ${role}` : who;
}

export default function AdminDocumentViewsPage() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [filters, setFilters] = useState<FilterState>(emptyFilters);
  const [applied, setApplied] = useState<FilterState>(emptyFilters);
  const [items, setItems] = useState<DocumentViewActivityItem[]>([]);
  const [summary, setSummary] = useState<DocumentViewPlatformSummary | null>(
    null,
  );
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const [detailDoc, setDetailDoc] = useState<DocumentViewActivityItem | null>(
    null,
  );
  const [detailEvents, setDetailEvents] = useState<AuditEventItem[]>([]);
  const [detailStatus, setDetailStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [detailError, setDetailError] = useState<string | null>(null);

  const load = useCallback(
    async (nextPage: number, nextFilters: FilterState, signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listAdminDocumentViewsRequest(
          accessToken,
          {
            page: nextPage,
            page_size: 20,
            q: nextFilters.q.trim() || undefined,
            owner_id: nextFilters.owner_id.trim() || undefined,
            viewer_id: nextFilters.viewer_id.trim() || undefined,
            created_from: nextFilters.created_from
              ? new Date(nextFilters.created_from).toISOString()
              : undefined,
            created_to: nextFilters.created_to
              ? new Date(nextFilters.created_to).toISOString()
              : undefined,
          },
          signal,
        );
        setItems(data.results);
        setSummary(data.summary ?? null);
        setPage(data.page);
        setTotalPages(data.total_pages);
        setTotal(data.total);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setItems([]);
        setError(
          err instanceof ApiError
            ? err.detail
            : "Unable to load document view activity.",
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

  async function openHistory(row: DocumentViewActivityItem) {
    if (!accessToken) return;
    setDetailDoc(row);
    setDetailStatus("loading");
    setDetailError(null);
    try {
      const data = await listAuditEventsRequest(accessToken, {
        page: 1,
        page_size: 50,
        document_id: row.document_id,
        action: "DOCUMENT_VIEW",
        outcome: "SUCCESS",
      });
      setDetailEvents(data.results);
      setDetailStatus("ready");
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setDetailEvents([]);
      setDetailError(
        err instanceof ApiError ? err.detail : "Unable to load view history.",
      );
      setDetailStatus("error");
    }
  }

  function onApply(event: FormEvent) {
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

      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Document views
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
          Platform view audit
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Authorised preview requests only. Admin role does not grant permission
          to open confidential file contents. Distinct viewers ≠ total view
          events.
        </p>
      </header>

      {summary ? (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]">
            <p className="text-xs uppercase tracking-wide text-muted">
              Total view events
            </p>
            <p className="mt-2 font-display text-3xl">
              {summary.total_view_events}
            </p>
          </div>
          <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]">
            <p className="text-xs uppercase tracking-wide text-muted">
              Documents with views
            </p>
            <p className="mt-2 font-display text-3xl">
              {summary.documents_with_views}
            </p>
          </div>
          <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)] sm:col-span-2 lg:col-span-1">
            <p className="text-xs uppercase tracking-wide text-muted">
              Most viewed
            </p>
            {summary.most_viewed.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No views yet.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {summary.most_viewed.map((row) => (
                  <li key={row.document_id}>
                    <span className="font-medium">{row.title}</span>
                    <span className="text-muted"> · {row.total_views}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      ) : null}

      <form
        onSubmit={onApply}
        className="grid gap-3 rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)] sm:grid-cols-2 lg:grid-cols-3"
      >
        <label className="text-sm sm:col-span-2">
          <span className="text-xs uppercase tracking-wide text-muted">
            Search title / owner
          </span>
          <input
            value={filters.q}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, q: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
            placeholder="Policy brief"
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
            placeholder="UUID"
          />
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            Viewer ID
          </span>
          <input
            value={filters.viewer_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, viewer_id: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border px-3 py-2"
            placeholder="UUID"
          />
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">From</span>
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
          <span className="text-xs uppercase tracking-wide text-muted">To</span>
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
        <p className="text-sm text-muted">Loading document views…</p>
      ) : null}
      {status === "error" ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      {status === "ready" && items.length === 0 ? (
        <p className="text-sm text-muted">No documents match these filters.</p>
      ) : null}

      {status === "ready" && items.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-3 font-semibold">Document</th>
                <th className="px-3 py-3 font-semibold">Owner</th>
                <th className="px-3 py-3 font-semibold">Views</th>
                <th className="px-3 py-3 font-semibold">Distinct</th>
                <th className="px-3 py-3 font-semibold">Latest</th>
                <th className="px-3 py-3 font-semibold">History</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.document_id} className="border-b border-border/70">
                  <td className="px-3 py-3">
                    <p className="font-medium">{row.title}</p>
                    <p className="break-all font-mono text-[11px] text-muted">
                      {row.document_id}
                    </p>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted">
                    {row.owner_name}
                    <br />
                    {row.owner_email}
                  </td>
                  <td className="px-3 py-3 font-semibold">{row.total_views}</td>
                  <td className="px-3 py-3">{row.distinct_viewers}</td>
                  <td className="px-3 py-3 text-muted">
                    {row.latest_view_at
                      ? formatDateTime(row.latest_view_at)
                      : "—"}
                  </td>
                  <td className="px-3 py-3">
                    <button
                      type="button"
                      onClick={() => void openHistory(row)}
                      className="text-xs font-semibold text-accent-strong underline"
                    >
                      Who viewed
                    </button>
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
            Page {page} of {totalPages} ({total} documents)
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

      {detailDoc ? (
        <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-display text-xl text-foreground">
                View history — {detailDoc.title}
              </h2>
              <p className="mt-1 text-sm text-muted">
                Metadata only. This panel does not open the confidential file.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setDetailDoc(null);
                setDetailEvents([]);
                setDetailStatus("idle");
              }}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold"
            >
              Close
            </button>
          </div>
          {detailStatus === "loading" ? (
            <p className="mt-3 text-sm text-muted">Loading viewers…</p>
          ) : null}
          {detailError ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              {detailError}
            </p>
          ) : null}
          {detailStatus === "ready" && detailEvents.length === 0 ? (
            <p className="mt-3 text-sm text-muted">No successful views recorded.</p>
          ) : null}
          {detailStatus === "ready" && detailEvents.length > 0 ? (
            <ul className="mt-3 max-h-80 space-y-2 overflow-auto text-sm">
              {detailEvents.map((event) => (
                <li
                  key={event.id}
                  className="rounded-md border border-border/70 px-3 py-2"
                >
                  <p className="font-medium">{viewerLabel(event)}</p>
                  <p className="text-xs text-muted">
                    {formatDateTime(event.created_at)} · {event.outcome}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
