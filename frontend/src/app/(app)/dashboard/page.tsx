"use client";

import { FilePlus2, FolderOpen, Share2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { FileTypeIcon } from "@/components/file-type-icon";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClassName } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader, SectionHeading } from "@/components/ui/page-header";
import { Panel, StatCard } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  listDocumentsRequest,
  type DocumentListItem,
} from "@/lib/api";
import { formatDocumentAccessLabel } from "@/lib/document-access";
import { formatDateTime, mimeLabel } from "@/lib/format";
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
  const [reloadTick, setReloadTick] = useState(0);
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
  }, [accessToken, handleUnauthorized, user, reloadTick]);

  if (!user || user.role === "ADMIN") {
    return (
      <p className="text-sm text-muted" role="status">
        Redirecting to your workspace…
      </p>
    );
  }

  const isOwner = user.role === "OWNER";
  const firstName = user.name.trim().split(/\s+/)[0] || user.name;

  return (
    <div className="space-y-6">
      <PageHeader
        accentTitle
        title={`Welcome back, ${firstName}`}
        description={
          isOwner
            ? "Your owned and shared documents at a glance."
            : "Documents shared with your account."
        }
        actions={
          isOwner ? (
            <Link
              href="/documents/upload"
              className={buttonClassName({ variant: "primary" })}
            >
              <FilePlus2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              Upload document
            </Link>
          ) : (
            <Link
              href="/shared"
              className={buttonClassName({ variant: "primary" })}
            >
              <Share2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              Shared documents
            </Link>
          )
        }
      />

      {summary.status === "error" ? (
        <Alert
          tone="error"
          action={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setReloadTick((value) => value + 1)}
            >
              Retry
            </Button>
          }
        >
          {summary.error}
        </Alert>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2">
        {isOwner ? (
          <Link
            href="/documents"
            className="block rounded-[var(--radius)] transition-shadow duration-[180ms] hover:shadow-[var(--shadow)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <StatCard
              label="Documents you own"
              value={
                summary.status === "loading"
                  ? "…"
                  : summary.ownedTotal === null
                    ? "—"
                    : summary.ownedTotal
              }
              icon={<FolderOpen className="h-4 w-4" strokeWidth={1.75} />}
              className="hover:border-accent/40"
            />
          </Link>
        ) : null}
        <Link
          href="/shared"
          className="block rounded-[var(--radius)] transition-shadow duration-[180ms] hover:shadow-[var(--shadow)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          <StatCard
            label="Shared with you"
            value={
              summary.status === "loading"
                ? "…"
                : summary.sharedTotal === null
                  ? "—"
                  : summary.sharedTotal
            }
            icon={<Share2 className="h-4 w-4" strokeWidth={1.75} />}
            className="hover:border-accent/40"
          />
        </Link>
      </section>

      <Panel>
        <SectionHeading
          title={
            isOwner ? "Recent owned documents" : "Recent shared documents"
          }
          actions={
            <Link
              href={isOwner ? "/documents" : "/shared"}
              className="text-sm font-semibold text-accent-strong hover:underline"
            >
              View all
            </Link>
          }
        />

        {summary.status === "loading" ? (
          <div className="mt-4 space-y-3" aria-busy role="status">
            <Skeleton className="h-14 w-full rounded-[0.75rem]" />
            <Skeleton className="h-14 w-full rounded-[0.75rem]" />
            <Skeleton className="h-14 w-[70%] rounded-[0.75rem]" />
            <span className="sr-only">Loading…</span>
          </div>
        ) : summary.status === "error" ? null : summary.recent.length === 0 ? (
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
              icon={
                isOwner ? (
                  <FolderOpen className="h-5 w-5" strokeWidth={1.75} />
                ) : (
                  <Share2 className="h-5 w-5" strokeWidth={1.75} />
                )
              }
              action={
                isOwner ? (
                  <Link
                    href="/documents/upload"
                    className={buttonClassName({ variant: "primary" })}
                  >
                    Upload document
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
                className="flex flex-wrap items-center justify-between gap-3 py-3"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
                    <FileTypeIcon mime={doc.mime_type} />
                  </span>
                  <div className="min-w-0">
                    <Link
                      href={`/documents/${doc.id}`}
                      className="font-medium text-foreground hover:text-accent-strong"
                    >
                      {doc.title}
                    </Link>
                    <p className="mt-0.5 text-xs text-muted">
                      {doc.category}
                      {" · "}
                      {mimeLabel(doc.mime_type)}
                      {" · "}
                      {formatDateTime(doc.created_at)}
                    </p>
                  </div>
                </div>
                {!isOwner ? (
                  <Badge
                    tone={
                      doc.your_access === "EDIT" || doc.your_access === "OWNER"
                        ? "accent"
                        : "neutral"
                    }
                  >
                    {formatDocumentAccessLabel(doc.your_access)}
                  </Badge>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {isOwner ? (
        <p className="text-sm text-muted">
          Review how others open your files in{" "}
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
