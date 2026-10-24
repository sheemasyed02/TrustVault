"use client";

import { Eye } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button, buttonClassName } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { StatCard } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  listOwnerDocumentViewActivityRequest,
  type DocumentViewActivityItem,
  type DocumentViewPlatformSummary,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { getPostLoginPath } from "@/lib/nav";

/**
 * Owner document-view activity dashboard.
 * Counts come from persisted DOCUMENT_VIEW SUCCESS audit rows only.
 */
export default function OwnerActivityPage() {
  const { user, accessToken } = useAuth();
  const router = useRouter();
  const handleUnauthorized = useHandleUnauthorized();
  const [items, setItems] = useState<DocumentViewActivityItem[]>([]);
  const [summary, setSummary] = useState<DocumentViewPlatformSummary | null>(
    null,
  );
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    if (user.role !== "OWNER") {
      router.replace(getPostLoginPath(user.role));
    }
  }, [router, user]);

  const load = useCallback(
    async (nextPage: number, signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listOwnerDocumentViewActivityRequest(
          accessToken,
          { page: nextPage, page_size: 20 },
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
    if (!accessToken || user?.role !== "OWNER") return;
    const controller = new AbortController();
    void load(1, controller.signal);
    return () => controller.abort();
  }, [accessToken, load, user?.role]);

  if (!user || user.role !== "OWNER") {
    return (
      <p className="text-sm text-muted" role="status">
        Redirecting...
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="External views"
        description="How often others open your files. Your own opens remain in the security trail but are not counted here."
      />

      {summary ? (
        <dl className="grid gap-3 sm:grid-cols-2">
          <StatCard
            label="Total external view events"
            value={String(summary.total_view_events)}
            icon={<Eye className="h-4 w-4" strokeWidth={1.75} />}
          />
          <StatCard
            label="Documents with external views"
            value={String(summary.documents_with_views)}
          />
        </dl>
      ) : null}

      {status === "loading" ? (
        <div className="space-y-2" role="status" aria-busy>
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full rounded-[0.75rem]" />
          ))}
          <span className="sr-only">Loading view activity...</span>
        </div>
      ) : null}

      {status === "error" ? (
        <Alert
          tone="error"
          action={
            <Button size="sm" variant="secondary" onClick={() => void load(page)}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {status === "ready" && items.length === 0 ? (
        <EmptyState
          title="No owned documents yet"
          description="Upload a document to start collecting authorised view history."
          icon={<Eye className="h-5 w-5" strokeWidth={1.75} />}
          action={
            <Link
              href="/documents/upload"
              className={buttonClassName({ variant: "primary" })}
            >
              Upload a document
            </Link>
          }
        />
      ) : null}

      {status === "ready" && items.length > 0 ? (
        <div className="tv-table-wrap">
          <table className="tv-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>External views</th>
                <th className="hidden sm:table-cell">Distinct viewers</th>
                <th className="hidden md:table-cell">Latest external view</th>
                <th>History</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.document_id}>
                  <td>
                    <Link
                      href={`/documents/${row.document_id}`}
                      className="font-medium text-foreground hover:text-accent-strong"
                    >
                      {row.title}
                    </Link>
                    <p className="mt-1 text-xs text-muted sm:hidden">
                      {row.distinct_viewers} distinct
                      {row.latest_view_at
                        ? ` · ${formatDateTime(row.latest_view_at)}`
                        : ""}
                    </p>
                  </td>
                  <td className="font-semibold">{row.total_views}</td>
                  <td className="hidden sm:table-cell">{row.distinct_viewers}</td>
                  <td className="hidden text-muted md:table-cell">
                    {row.latest_view_at
                      ? formatDateTime(row.latest_view_at)
                      : "—"}
                  </td>
                  <td>
                    <Link
                      href={`/documents/${row.document_id}#document-activity`}
                      className="text-xs font-semibold text-accent-strong hover:underline"
                    >
                      Open history
                    </Link>
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
              onClick={() => void load(page - 1)}
            >
              Previous
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => void load(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
