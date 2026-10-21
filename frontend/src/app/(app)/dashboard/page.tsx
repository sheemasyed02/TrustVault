"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listDocumentsRequest,
  type DocumentListItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { getPostLoginPath } from "@/lib/nav";

interface SummaryState {
  status: "loading" | "ready" | "error";
  ownedTotal: number | null;
  sharedTotal: number | null;
  recent: DocumentListItem[];
  error: string | null;
}

/**
 * Owner document-management dashboard.
 * ADMIN / VIEWER are redirected to their role homes.
 */
export default function DashboardPage() {
  const { user, accessToken } = useAuth();
  const router = useRouter();
  const handleUnauthorized = useHandleUnauthorized();
  const [summary, setSummary] = useState<SummaryState>({
    status: "loading",
    ownedTotal: null,
    sharedTotal: null,
    recent: [],
    error: null,
  });

  useEffect(() => {
    if (!user) return;
    if (user.role !== "OWNER") {
      router.replace(getPostLoginPath(user.role));
    }
  }, [router, user]);

  useEffect(() => {
    if (!accessToken || !user || user.role !== "OWNER") return;
    const token = accessToken;
    const currentUser = user;
    const controller = new AbortController();

    async function load() {
      setSummary((prev) => ({ ...prev, status: "loading", error: null }));
      try {
        const [owned, shared] = await Promise.all([
          listDocumentsRequest(
            token,
            { owner_id: currentUser.id, page: 1, page_size: 5 },
            controller.signal,
          ),
          listDocumentsRequest(
            token,
            { shared_only: true, page: 1, page_size: 5 },
            controller.signal,
          ),
        ]);
        setSummary({
          status: "ready",
          ownedTotal: owned.total,
          sharedTotal: shared.total,
          recent: owned.results,
          error: null,
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (handleUnauthorized(error)) return;
        setSummary({
          status: "error",
          ownedTotal: null,
          sharedTotal: null,
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

  if (!user || user.role !== "OWNER") {
    return (
      <p className="text-sm text-muted" role="status">
        Redirecting to your workspace…
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Owner dashboard
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
          Welcome, {user.name}
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Manage documents you own, upload new files, and share READ or EDIT
          access with registered users. Counts come from the authorized list API.
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
          hint="GET /documents?owner_id=you"
        />
        <SummaryCard
          label="Shared with you"
          value={summary.sharedTotal}
          loading={summary.status === "loading"}
          hint="GET /documents?shared_only=true"
        />
        <article className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">
            Quick actions
          </p>
          <div className="mt-3 flex flex-col gap-2 text-sm">
            <Link
              href="/documents/upload"
              className="font-semibold text-accent-strong hover:underline"
            >
              Upload a document
            </Link>
            <Link
              href="/documents"
              className="font-semibold text-accent-strong hover:underline"
            >
              My Documents
            </Link>
            <Link
              href="/shared"
              className="font-semibold text-accent-strong hover:underline"
            >
              Shared with me
            </Link>
          </div>
        </article>
      </section>

      <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl text-foreground">
            Recent owned documents
          </h2>
          <Link
            href="/documents"
            className="text-sm font-semibold text-accent-strong hover:underline"
          >
            View all
          </Link>
        </div>
        {summary.status === "loading" ? (
          <p className="mt-4 text-sm text-muted">Loading recent documents…</p>
        ) : summary.recent.length === 0 ? (
          <p className="mt-4 text-sm text-muted">
            No owned documents yet.{" "}
            <Link
              href="/documents/upload"
              className="font-semibold text-accent-strong hover:underline"
            >
              Upload your first file
            </Link>
            .
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
