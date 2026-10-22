"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import {
  ApiError,
  listDocumentsRequest,
  type DocumentListItem,
} from "@/lib/api";
import { formatDocumentAccessLabel } from "@/lib/document-access";
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
 * Role-aware home dashboard.
 * ADMIN is redirected to /admin. OWNER and VIEWER see task-focused summaries.
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
    if (user.role === "ADMIN") {
      router.replace(getPostLoginPath(user.role));
    }
  }, [router, user]);

  useEffect(() => {
    if (!accessToken || !user || user.role === "ADMIN") return;
    const token = accessToken;
    const currentUser = user;
    const controller = new AbortController();

    async function load() {
      setSummary((prev) => ({ ...prev, status: "loading", error: null }));
      try {
        if (currentUser.role === "OWNER") {
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
        } else {
          const shared = await listDocumentsRequest(
            token,
            { shared_only: true, page: 1, page_size: 8 },
            controller.signal,
          );
          setSummary({
            status: "ready",
            ownedTotal: null,
            sharedTotal: shared.total,
            recent: shared.results,
            error: null,
          });
        }
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

  if (!user || user.role === "ADMIN") {
    return (
      <p className="text-sm text-muted" role="status">
        Redirecting to your workspace…
      </p>
    );
  }

  const isOwner = user.role === "OWNER";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={isOwner ? "Owner" : "Viewer"}
        title={`Welcome, ${user.name}`}
        description={
          isOwner
            ? "Upload, organize, and share documents you own."
            : "Open documents that have been shared with your account."
        }
        actions={
          isOwner ? (
            <Link
              href="/documents/upload"
              className="inline-flex items-center justify-center rounded-md bg-accent px-3.5 py-2 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Upload document
            </Link>
          ) : (
            <Link
              href="/shared"
              className="inline-flex items-center justify-center rounded-md bg-accent px-3.5 py-2 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Shared documents
            </Link>
          )
        }
      />

      {summary.status === "error" ? (
        <Alert tone="error">{summary.error}</Alert>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2">
        {isOwner ? (
          <StatCard
            label="Documents you own"
            value={summary.ownedTotal}
            loading={summary.status === "loading"}
            href="/documents"
          />
        ) : null}
        <StatCard
          label="Shared with you"
          value={summary.sharedTotal}
          loading={summary.status === "loading"}
          href="/shared"
        />
      </section>

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl text-foreground">
            {isOwner ? "Recent owned documents" : "Recent shared documents"}
          </h2>
          <Link
            href={isOwner ? "/documents" : "/shared"}
            className="text-sm font-semibold text-accent-strong hover:underline"
          >
            View all
          </Link>
        </div>

        {summary.status === "loading" ? (
          <p className="mt-4 text-sm text-muted">Loading…</p>
        ) : summary.recent.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title={
                isOwner ? "No documents yet" : "Nothing shared with you yet"
              }
              description={
                isOwner
                  ? "Upload a DOCX file to get started."
                  : "When someone grants you READ or EDIT access, documents appear here."
              }
              action={
                isOwner ? (
                  <Link
                    href="/documents/upload"
                    className="inline-flex items-center justify-center rounded-md bg-accent px-3.5 py-2 text-sm font-semibold text-white hover:bg-accent-strong"
                  >
                    Upload
                  </Link>
                ) : null
              }
            />
          </div>
        ) : (
          <ul className="mt-4 divide-y divide-border">
            {summary.recent.map((doc) => (
              <li
                key={doc.id}
                className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
              >
                <div className="min-w-0">
                  <Link
                    href={`/documents/${doc.id}`}
                    className="font-medium text-foreground hover:text-accent-strong"
                  >
                    {doc.title}
                  </Link>
                  <p className="mt-0.5 text-xs text-muted">
                    {doc.category}
                    {!isOwner
                      ? ` · ${formatDocumentAccessLabel(doc.your_access)}`
                      : null}
                    {" · "}
                    {formatDateTime(doc.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {isOwner ? (
        <p className="text-sm text-muted">
          Track how others open your files in{" "}
          <Link
            href="/activity"
            className="font-semibold text-accent-strong hover:underline"
          >
            Document Activity
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}

function StatCard({
  label,
  value,
  loading,
  href,
}: {
  label: string;
  value: number | null;
  loading: boolean;
  href: string;
}) {
  return (
    <Link href={href} className="block">
      <Panel className="transition-colors hover:border-accent/40">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          {label}
        </p>
        <p className="mt-2 font-display text-3xl text-foreground">
          {loading ? "…" : value === null ? "—" : value}
        </p>
      </Panel>
    </Link>
  );
}
