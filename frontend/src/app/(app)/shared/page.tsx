"use client";

import { Share2 } from "lucide-react";
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
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
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

  const hasActiveFilters =
    Boolean(filters.title) ||
    Boolean(filters.category) ||
    Boolean(filters.createdFrom) ||
    Boolean(filters.createdTo);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Shared with you"
        description="Documents others have granted you access to. Your access level is shown on each item."
      />

      <DocumentFilters value={filters} onChange={setFilters} />

      {actions.actionError ? (
        <Alert tone="error">{actions.actionError}</Alert>
      ) : null}
      {actions.actionMessage ? (
        <Alert tone="success">{actions.actionMessage}</Alert>
      ) : null}

      {list.status === "loading" || list.status === "idle" ? (
        <DocumentTableSkeleton />
      ) : null}

      {list.status === "error" ? (
        <Alert
          tone="error"
          action={
            <Button size="sm" variant="secondary" onClick={() => list.refresh()}>
              Retry
            </Button>
          }
        >
          {list.errorMessage}
        </Alert>
      ) : null}

      {list.status === "empty" ? (
        <EmptyState
          title={
            hasActiveFilters ? "No matching shared documents" : "No shared documents"
          }
          description={
            hasActiveFilters
              ? "Try clearing filters or adjusting your search."
              : "When an owner grants you READ or EDIT access, documents appear here."
          }
          icon={<Share2 className="h-5 w-5" strokeWidth={1.75} />}
          action={
            hasActiveFilters ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  setFilters({
                    title: "",
                    category: "",
                    createdFrom: "",
                    createdTo: "",
                  })
                }
              >
                Clear filters
              </Button>
            ) : null
          }
        />
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
