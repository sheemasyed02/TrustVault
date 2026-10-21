"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listDocumentsRequest,
  type DocumentListItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface SummaryState {
  status: "loading" | "ready" | "error";
  ownedTotal: number | null;
  accessibleTotal: number | null;
  recent: DocumentListItem[];
  error: string | null;
}

export default function DashboardPage() {
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [summary, setSummary] = useState<SummaryState>({
    status: "loading",
    ownedTotal: null,
    accessibleTotal: null,
    recent: [],
    error: null,
  });

  useEffect(() => {
    if (!accessToken || !user) return;
    const token = accessToken;
    const currentUser = user;
    const controller = new AbortController();

    async function load() {
      setSummary((prev) => ({ ...prev, status: "loading", error: null }));
      try {
        const [owned, accessible] = await Promise.all([
          listDocumentsRequest(
            token,
            { owner_id: currentUser.id, page: 1, page_size: 5 },
            controller.signal,
          ),
          listDocumentsRequest(
            token,
            { page: 1, page_size: 5 },
            controller.signal,
          ),
        ]);
        setSummary({
          status: "ready",
          ownedTotal: owned.total,
          accessibleTotal: accessible.total,
          recent: accessible.results,
          error: null,
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (handleUnauthorized(error)) return;
        setSummary({
          status: "error",
          ownedTotal: null,
          accessibleTotal: null,
          recent: [],
          error:
            error instanceof ApiError
              ? error.detail
              : "Unable to load dashboard summary.",
        });
      }
    }

    void load();
    return () => controller.abort();
  }, [accessToken, handleUnauthorized, user]);

  const sharedEstimate =
    summary.ownedTotal !== null && summary.accessibleTotal !== null
      ? Math.max(0, summary.accessibleTotal - summary.ownedTotal)
      : null;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Dashboard
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
          Welcome, {user?.name}
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Counts below come from the document list API totals (server-authorized).
          There is no separate activity feed endpoint yet, so recent items use the
          newest accessible documents.
        </p>
      </header>

      {summary.status === "error" ? (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger"
        >
          {summary.error}
        </div>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          label="Documents you own"
          value={summary.ownedTotal}
          loading={summary.status === "loading"}
          hint="GET /documents?owner_id=you → total"
        />
        <SummaryCard
          label="Shared with you (estimate)"
          value={sharedEstimate}
          loading={summary.status === "loading"}
          hint="accessible total minus owned total (no dedicated shared endpoint)"
        />
        <SummaryCard
          label="All accessible"
          value={summary.accessibleTotal}
          loading={summary.status === "loading"}
          hint="GET /documents → total"
        />
      </section>

      <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl text-foreground">Recent documents</h2>
          <Link
            href="/documents"
            className="text-sm font-semibold text-accent-strong hover:underline"
          >
            View my documents
          </Link>
        </div>
        {summary.status === "loading" ? (
          <p className="mt-4 text-sm text-muted">Loading recent documents…</p>
        ) : summary.recent.length === 0 ? (
          <p className="mt-4 text-sm text-muted">
            No accessible documents yet. Owners can upload in a later task screen.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-border">
            {summary.recent.map((doc) => (
              <li
                key={doc.id}
                className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
              >
                <Link
                  href={`/documents/${doc.id}`}
                  className="font-medium text-foreground hover:text-accent-strong"
                >
                  {doc.title}
                </Link>
                <span className="text-muted">
                  {doc.category} · {formatDateTime(doc.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  loading,
  hint,
}: {
  label: string;
  value: number | null;
  loading: boolean;
  hint: string;
}) {
  return (
    <article className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">
        {label}
      </p>
      <p className="mt-3 font-display text-3xl text-foreground">
        {loading ? "…" : value === null ? "—" : value}
      </p>
      <p className="mt-2 text-xs leading-5 text-muted">{hint}</p>
    </article>
  );
}
