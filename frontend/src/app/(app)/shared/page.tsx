"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  DocumentFilters,
  toApiDateBound,
  type DocumentFilterValues,
} from "@/components/document-filters";
import {
  DocumentTable,
  DocumentTableSkeleton,
  PaginationBar,
} from "@/components/document-table";
import { useDocumentActions } from "@/hooks/use-document-actions";
import { useDocumentList } from "@/hooks/use-document-list";

/**
 * Shared With Me reuses GET /documents (no dedicated shared endpoint).
 * We show rows where owner.id !== current user. Permission level (READ/EDIT)
 * is not returned by the list API yet — that is a backend gap.
 */
export default function SharedWithMePage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState<DocumentFilterValues>({
    title: "",
    category: "",
    createdFrom: "",
    createdTo: "",
  });

  const listParams = useMemo(
    () => ({
      title: filters.title.trim() || undefined,
      category: filters.category.trim() || undefined,
      created_from: toApiDateBound(filters.createdFrom, false),
      created_to: toApiDateBound(filters.createdTo, true),
      page_size: 20,
    }),
    [filters],
  );

  const list = useDocumentList(listParams, { enabled: Boolean(user) });
  const actions = useDocumentActions(() => list.refresh());

  const sharedOnPage = useMemo(() => {
    if (!user) return [];
    return list.results.filter((doc) => doc.owner.id !== user.id);
  }, [list.results, user]);

  if (!user) return null;

  return (
    <div className="space-y-5">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Shared with me
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight">
          Documents others shared with you
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          The backend has no separate Shared With Me route. This page calls the
          authorized list API, then shows only documents you do not own. READ vs
          EDIT labels are unavailable until the API returns grant level.
        </p>
      </header>

      <DocumentFilters value={filters} onChange={setFilters} />

      {actions.actionError ? (
        <p role="alert" className="text-sm text-danger">
          {actions.actionError}
        </p>
      ) : null}

      {list.status === "loading" || list.status === "idle" ? (
        <DocumentTableSkeleton />
      ) : null}

      {list.status === "error" ? (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-4 text-sm"
        >
          <p className="text-danger">{list.errorMessage}</p>
          <button
            type="button"
            onClick={() => list.refresh()}
            className="mt-3 rounded-md border border-border bg-white px-3 py-1.5 text-xs font-semibold"
          >
            Retry
          </button>
        </div>
      ) : null}

      {list.status === "ready" || list.status === "empty" ? (
        sharedOnPage.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center">
            <p className="font-medium text-foreground">
              No shared documents on this page
            </p>
            <p className="mt-2 text-sm text-muted">
              {list.total === 0
                ? "Nothing has been shared with you yet (authorized list is empty)."
                : "This server page may only contain documents you own. Try Next, or clear filters."}
            </p>
            {list.totalPages > 1 ? (
              <div className="mt-4">
                <PaginationBar
                  page={list.page}
                  totalPages={list.totalPages}
                  total={list.total}
                  onPageChange={list.setPage}
                />
              </div>
            ) : null}
          </div>
        ) : (
          <>
            <p className="text-xs text-muted">
              Showing {sharedOnPage.length} shared document(s) from this API page
              (server page total includes owned docs too: {list.total}).
            </p>
            <DocumentTable
              documents={sharedOnPage}
              currentUser={user}
              mode="shared"
              downloadingId={actions.downloadingId}
              onDownload={(doc) => void actions.download(doc)}
            />
            <PaginationBar
              page={list.page}
              totalPages={list.totalPages}
              total={list.total}
              onPageChange={list.setPage}
            />
          </>
        )
      ) : null}
    </div>
  );
}
