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

export default function MyDocumentsPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState<DocumentFilterValues>({
    title: "",
    category: "",
    createdFrom: "",
    createdTo: "",
  });

  const listParams = useMemo(
    () => ({
      owner_id: user?.id,
      title: filters.title.trim() || undefined,
      category: filters.category.trim() || undefined,
      created_from: toApiDateBound(filters.createdFrom, false),
      created_to: toApiDateBound(filters.createdTo, true),
      page_size: 20,
    }),
    [filters, user?.id],
  );

  const list = useDocumentList(listParams, { enabled: Boolean(user) });
  const actions = useDocumentActions(() => list.refresh());

  if (!user) return null;

  return (
    <div className="space-y-5">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          My Documents
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight">
          Documents you own
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Loaded with <code className="text-xs">owner_id</code> set to your user
          id so the API returns only your owned documents (still authorization-checked
          server-side).
        </p>
      </header>

      <DocumentFilters
        value={filters}
        onChange={setFilters}
        showOwnerHint="Owner filter is fixed to your account for this page."
      />

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
          <p className="font-medium text-foreground">No owned documents found</p>
          <p className="mt-2 text-sm text-muted">
            Upload is not on this screen yet. When you have uploads, they will appear
            here from the live API.
          </p>
        </div>
      ) : null}

      {list.status === "ready" ? (
        <>
          <DocumentTable
            documents={list.results}
            currentUser={user}
            mode="owned"
            downloadingId={actions.downloadingId}
            onDownload={(doc) => void actions.download(doc)}
            onDelete={(doc) => void actions.remove(doc)}
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
