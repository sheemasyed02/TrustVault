"use client";

import { Eye } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader, SectionHeading } from "@/components/ui/page-header";
import { Panel, StatCard } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
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

      <PageHeader
        title="Platform view audit"
        description="Authorised preview requests only. Admin role does not grant permission to open confidential file contents. Distinct viewers are not the same as total view events."
      />

      {summary ? (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard
            label="Total view events"
            value={String(summary.total_view_events)}
            icon={<Eye className="h-4 w-4" strokeWidth={1.75} />}
          />
          <StatCard
            label="Documents with views"
            value={String(summary.documents_with_views)}
          />
          <Panel className="!p-4 sm:col-span-2 lg:col-span-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              Most viewed
            </p>
            {summary.most_viewed.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No views yet.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {summary.most_viewed.map((row) => (
                  <li key={row.document_id} className="truncate">
                    <span className="font-medium text-foreground">
                      {row.title}
                    </span>
                    <span className="text-muted"> · {row.total_views}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </section>
      ) : null}

      <form
        onSubmit={onApply}
        className="grid gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-sm)] sm:grid-cols-2 lg:grid-cols-3 sm:p-5"
      >
        <label className="text-sm sm:col-span-2">
          <span className="tv-label">Search title / owner</span>
          <input
            value={filters.q}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, q: e.target.value }))
            }
            className="tv-input"
            placeholder="Policy brief"
          />
        </label>
        <label className="text-sm">
          <span className="tv-label">Owner ID</span>
          <input
            value={filters.owner_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, owner_id: e.target.value }))
            }
            className="tv-input"
            placeholder="UUID"
          />
        </label>
        <label className="text-sm">
          <span className="tv-label">Viewer ID</span>
          <input
            value={filters.viewer_id}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, viewer_id: e.target.value }))
            }
            className="tv-input"
            placeholder="UUID"
          />
        </label>
        <label className="text-sm">
          <span className="tv-label">From</span>
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
          <span className="tv-label">To</span>
          <input
            type="datetime-local"
            value={filters.created_to}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, created_to: e.target.value }))
            }
            className="tv-input"
          />
        </label>
        <div className="flex flex-wrap items-end gap-2 sm:col-span-2 lg:col-span-3">
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
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full rounded-[0.75rem]" />
          ))}
          <span className="sr-only">Loading document views...</span>
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
          {error}
        </Alert>
      ) : null}

      {status === "ready" && items.length === 0 ? (
        <EmptyState
          title="No documents match"
          description="Adjust filters or wait for authorised preview activity."
          icon={<Eye className="h-5 w-5" strokeWidth={1.75} />}
        />
      ) : null}

      {status === "ready" && items.length > 0 ? (
        <div className="tv-table-wrap">
          <table className="tv-table">
            <thead>
              <tr>
                <th>Document</th>
                <th className="hidden md:table-cell">Owner</th>
                <th>Views</th>
                <th className="hidden sm:table-cell">Distinct</th>
                <th className="hidden lg:table-cell">Latest</th>
                <th>History</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.document_id}>
                  <td>
                    <p className="font-medium text-foreground">{row.title}</p>
                    <p
                      className="mt-0.5 max-w-[14rem] truncate font-mono text-[11px] text-muted"
                      title={row.document_id}
                    >
                      {row.document_id}
                    </p>
                    <p className="mt-1 text-xs text-muted md:hidden">
                      {row.owner_email}
                    </p>
                  </td>
                  <td className="hidden text-sm text-muted md:table-cell">
                    <span className="block font-medium text-foreground">
                      {row.owner_name}
                    </span>
                    <span className="block truncate text-xs">
                      {row.owner_email}
                    </span>
                  </td>
                  <td className="font-semibold">{row.total_views}</td>
                  <td className="hidden sm:table-cell">{row.distinct_viewers}</td>
                  <td className="hidden text-muted lg:table-cell">
                    {row.latest_view_at
                      ? formatDateTime(row.latest_view_at)
                      : "—"}
                  </td>
                  <td>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => void openHistory(row)}
                    >
                      Who viewed
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {status === "ready" && totalPages > 1 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius)] border border-border bg-surface px-4 py-3 text-sm shadow-[var(--shadow-sm)]">
          <p className="text-muted">
            Page {page} of {totalPages} ({total} documents)
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

      {detailDoc ? (
        <Panel>
          <SectionHeading
            title={`View history — ${detailDoc.title}`}
            description="Metadata only. This panel does not open the confidential file."
            actions={
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => {
                  setDetailDoc(null);
                  setDetailEvents([]);
                  setDetailStatus("idle");
                }}
              >
                Close
              </Button>
            }
          />
          {detailStatus === "loading" ? (
            <p className="mt-3 text-sm text-muted" role="status">
              Loading viewers...
            </p>
          ) : null}
          {detailError ? (
            <div className="mt-3">
              <Alert tone="error">{detailError}</Alert>
            </div>
          ) : null}
          {detailStatus === "ready" && detailEvents.length === 0 ? (
            <p className="mt-3 text-sm text-muted">No successful views recorded.</p>
          ) : null}
          {detailStatus === "ready" && detailEvents.length > 0 ? (
            <ul className="mt-3 max-h-80 space-y-2 overflow-auto text-sm">
              {detailEvents.map((event) => (
                <li
                  key={event.id}
                  className="rounded-[0.625rem] border border-border px-3 py-2"
                >
                  <p className="font-medium text-foreground">
                    {viewerLabel(event)}
                  </p>
                  <p className="text-xs text-muted">
                    {formatDateTime(event.created_at)} · {event.outcome}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}
