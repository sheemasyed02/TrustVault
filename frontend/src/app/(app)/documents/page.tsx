"use client";

import { FilePlus2, FolderOpen } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
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
import { Button, buttonClassName } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { useDocumentActions } from "@/hooks/use-document-actions";
import { useDocumentList } from "@/hooks/use-document-list";
import { getPostLoginPath } from "@/lib/nav";

export default function MyDocumentsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [filters, setFilters] = useState<DocumentFilterValues>({
    title: "",
    category: "",
    createdFrom: "",
    createdTo: "",
  });

  useEffect(() => {
    if (!user) return;
    // VIEWER accounts do not upload/own via the product workflow.
    if (user.role === "VIEWER") {
      router.replace(getPostLoginPath(user.role));
    }
  }, [router, user]);

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

  const list = useDocumentList(listParams, {
    enabled: Boolean(user) && user?.role !== "VIEWER",
  });
  const actions = useDocumentActions(() => list.refresh());

  if (!user) return null;
  if (user.role === "VIEWER") {
    return (
      <p className="text-sm text-muted" role="status">
        Redirecting to shared documents?
      </p>
    );
  }

  const hasActiveFilters =
    Boolean(filters.title) ||
    Boolean(filters.category) ||
    Boolean(filters.createdFrom) ||
    Boolean(filters.createdTo);

  return (
    <div className="space-y-5">
      <PageHeader
        title="My documents"
        description="Search and open files you uploaded. Share access from each document."
        actions={
          user.role === "OWNER" ? (
            <Link
              href="/documents/upload"
              className={buttonClassName({
                variant: "primary",
                className: "shrink-0",
              })}
            >
              <FilePlus2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              Upload document
            </Link>
          ) : null
        }
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
          title={hasActiveFilters ? "No matching documents" : "No documents yet"}
          description={
            hasActiveFilters
              ? "Try clearing filters or adjusting your search."
              : "Upload a DOCX file to create your first document."
          }
          icon={<FolderOpen className="h-5 w-5" strokeWidth={1.75} />}
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
            ) : user.role === "OWNER" ? (
              <Link
                href="/documents/upload"
                className={buttonClassName({ variant: "primary" })}
              >
                Upload document
              </Link>
            ) : null
          }
        />
      ) : null}

      {list.status === "ready" ? (
        <>
          <DocumentTable
            documents={list.results}
            currentUser={user}
            mode="owned"
            downloadingId={actions.downloadingId}
            onDownload={(doc) => void actions.download(doc)}
            onDelete={(doc) => actions.requestDelete(doc)}
          />
          <PaginationBar
            page={list.page}
            totalPages={list.totalPages}
            total={list.total}
            onPageChange={list.setPage}
          />
        </>
      ) : null}

      <ConfirmDialog
        open={actions.pendingDelete !== null}
        title="Delete this document?"
        description="Deleting removes the document from normal access and attempts private storage cleanup."
        confirmLabel="Delete document"
        danger
        busy={actions.deleting}
        onCancel={actions.cancelDelete}
        onConfirm={() => void actions.confirmDelete()}
      />
    </div>
  );
}
