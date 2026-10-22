"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
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
        Redirecting…
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Document activity
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
          View counts for your documents
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Each count is a successfully authorised preview request after the
          server checked permissions. It does not prove someone read or
          understood the whole file. Downloads are separate.
        </p>
      </header>

      {summary ? (
        <dl className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Total authorised view events
            </dt>
            <dd className="mt-2 font-display text-3xl text-foreground">
              {summary.total_view_events}
            </dd>
          </div>
          <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Documents with views
            </dt>
            <dd className="mt-2 font-display text-3xl text-foreground">
              {summary.documents_with_views}
            </dd>
          </div>
        </dl>
      ) : null}

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading view activity…
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
            onClick={() => void load(page)}
          >
            Retry
          </button>
        </div>
      ) : null}

      {status === "ready" && items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center">
          <p className="font-medium text-foreground">No owned documents yet</p>
          <p className="mt-2 text-sm text-muted">
            Upload a document to start collecting authorised view history.
          </p>
          <Link
            href="/documents/upload"
            className="mt-4 inline-block font-semibold text-accent-strong underline"
          >
            Upload a document
          </Link>
        </div>
      ) : null}

      {status === "ready" && items.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3 font-semibold">Document</th>
                <th className="px-4 py-3 font-semibold">Views</th>
                <th className="px-4 py-3 font-semibold">Distinct viewers</th>
                <th className="px-4 py-3 font-semibold">Latest view</th>
                <th className="px-4 py-3 font-semibold">History</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.document_id} className="border-b border-border/70">
                  <td className="px-4 py-3">
                    <Link
                      href={`/documents/${row.document_id}`}
                      className="font-medium text-foreground hover:text-accent-strong"
                    >
                      {row.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-semibold">{row.total_views}</td>
                  <td className="px-4 py-3">{row.distinct_viewers}</td>
                  <td className="px-4 py-3 text-muted">
                    {row.latest_view_at
                      ? formatDateTime(row.latest_view_at)
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/documents/${row.document_id}#document-activity`}
                      className="text-xs font-semibold text-accent-strong underline"
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
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => void load(page - 1)}
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
            onClick={() => void load(page + 1)}
            className="rounded-md border border-border px-3 py-1.5 font-semibold disabled:opacity-50"
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}
