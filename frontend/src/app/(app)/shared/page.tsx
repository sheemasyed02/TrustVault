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
 * Shared With Me — GET /documents?shared_only=true.
 * Rows include your_access (READ | EDIT) from PostgreSQL.
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
      shared_only: true,
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

  if (!user) return null;

  return (
    <div className="space-y-5">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent-strong">
          Shared documents
        </p>
        <h1 className="mt-1.5 font-display text-2xl tracking-tight sm:text-3xl">
          Shared with you
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Documents others have granted you access to. Your access level is shown
          on each row.
        </p>
      </header>

      <DocumentFilters value={filters} onChange={setFilters} />

      {actions.actionError ? (
        <p role="alert" className="text-sm text-danger">
          {actions.actionError}
        </p>
      ) : null}
      {actions.actionMessage ? (
        <p role="status" className="text-sm text-accent-strong">
          {actions.actionMessage}
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

      {list.status === "empty" ? (
        <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center">
          <p className="font-medium text-foreground">No shared documents</p>
          <p className="mt-2 text-sm text-muted">
            When an owner grants you READ or EDIT access, documents appear here.
          </p>
        </div>
      ) : null}

      {list.status === "ready" ? (
        <>
          <DocumentTable
            documents={list.results}
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
      ) : null}
    </div>
  );
}
