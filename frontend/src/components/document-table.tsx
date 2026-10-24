"use client";

import { Download, LayoutGrid, List, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { FileTypeIcon } from "@/components/file-type-icon";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClassName } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMediaQuery } from "@/hooks/use-media-query";
import type {
  DocumentAccessLevel,
  DocumentListItem,
  UserPublic,
} from "@/lib/api";
import { formatDocumentAccessLabel } from "@/lib/document-access";
import { formatBytes, formatDateTime, mimeLabel } from "@/lib/format";

interface DocumentTableProps {
  documents: DocumentListItem[];
  currentUser: UserPublic;
  onDownload: (doc: DocumentListItem) => void;
  onDelete?: (doc: DocumentListItem) => void;
  downloadingId?: string | null;
  mode: "owned" | "shared" | "all";
}

export function DocumentTableSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" role="status">
      <div className="flex justify-end">
        <Skeleton className="h-8 w-24" />
      </div>
      {Array.from({ length: 5 }).map((_, index) => (
        <Skeleton key={index} className="h-16 w-full rounded-[var(--radius)]" />
      ))}
      <span className="sr-only">Loading documents…</span>
    </div>
  );
}

function AccessBadge({ level }: { level: DocumentAccessLevel }) {
  const tone =
    level === "EDIT" || level === "OWNER"
      ? ("accent" as const)
      : ("neutral" as const);
  return <Badge tone={tone}>{formatDocumentAccessLabel(level)}</Badge>;
}

function DocumentActions({
  doc,
  isOwner,
  downloadingId,
  onDownload,
  onDelete,
}: {
  doc: DocumentListItem;
  isOwner: boolean;
  downloadingId?: string | null;
  onDownload: (doc: DocumentListItem) => void;
  onDelete?: (doc: DocumentListItem) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Link
        href={`/documents/${doc.id}`}
        className={buttonClassName({
          variant: "secondary",
          size: "sm",
        })}
      >
        Open
      </Link>
      <Button
        size="sm"
        variant="secondary"
        onClick={() => onDownload(doc)}
        disabled={downloadingId === doc.id}
      >
        <Download className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        {downloadingId === doc.id ? "…" : "PDF"}
      </Button>
      {isOwner && onDelete ? (
        <Button size="sm" variant="danger" onClick={() => onDelete(doc)}>
          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          Delete
        </Button>
      ) : null}
    </div>
  );
}

function DocumentCard({
  doc,
  currentUser,
  mode,
  downloadingId,
  onDownload,
  onDelete,
}: {
  doc: DocumentListItem;
  currentUser: UserPublic;
  mode: DocumentTableProps["mode"];
  downloadingId?: string | null;
  onDownload: (doc: DocumentListItem) => void;
  onDelete?: (doc: DocumentListItem) => void;
}) {
  const isOwner =
    doc.your_access === "OWNER" || doc.owner.id === currentUser.id;
  const accessLabel = formatDocumentAccessLabel(doc.your_access);

  return (
    <article className="rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-sm)] transition-shadow duration-[180ms] hover:shadow-[var(--shadow)]">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[0.75rem] bg-accent-soft text-accent-strong">
          <FileTypeIcon mime={doc.mime_type} className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <Link
                href={`/documents/${doc.id}`}
                className="font-semibold text-foreground hover:text-accent-strong"
              >
                {doc.title}
              </Link>
              <span className="sr-only"> ({accessLabel})</span>
              <p className="mt-1 text-xs text-muted">
                {doc.category}
                {" · "}
                {mimeLabel(doc.mime_type)}
                {" · "}
                {formatBytes(doc.file_size)}
              </p>
            </div>
            {mode === "shared" || mode === "all" ? (
              <AccessBadge level={doc.your_access} />
            ) : null}
          </div>
          <p className="mt-2 text-xs text-muted">
            {mode !== "owned" ? (
              <>
                {doc.owner.name}
                {isOwner ? " (you)" : ""}
                {" · "}
              </>
            ) : null}
            {formatDateTime(doc.created_at)}
          </p>
          <div className="mt-3">
            <DocumentActions
              doc={doc}
              isOwner={isOwner}
              downloadingId={downloadingId}
              onDownload={onDownload}
              onDelete={onDelete}
            />
          </div>
        </div>
      </div>
    </article>
  );
}

export function DocumentTable({
  documents,
  currentUser,
  onDownload,
  onDelete,
  downloadingId,
  mode,
}: DocumentTableProps) {
  const [view, setView] = useState<"list" | "grid">("list");
  const isMobile = useMediaQuery("(max-width: 767px)");
  const showCards = isMobile || view === "grid";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">
          Showing {documents.length} document
          {documents.length === 1 ? "" : "s"}
        </p>
        <div
          className="hidden items-center rounded-[0.625rem] border border-border bg-surface p-0.5 sm:inline-flex"
          role="group"
          aria-label="Document layout"
        >
          <button
            type="button"
            aria-pressed={view === "list"}
            onClick={() => setView("list")}
            className={`inline-flex items-center gap-1.5 rounded-[0.5rem] px-2.5 py-1.5 text-xs font-semibold transition-colors duration-[180ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              view === "list"
                ? "bg-accent-soft text-accent-strong"
                : "text-muted hover:text-foreground"
            }`}
          >
            <List className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            List
          </button>
          <button
            type="button"
            aria-pressed={view === "grid"}
            onClick={() => setView("grid")}
            className={`inline-flex items-center gap-1.5 rounded-[0.5rem] px-2.5 py-1.5 text-xs font-semibold transition-colors duration-[180ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              view === "grid"
                ? "bg-accent-soft text-accent-strong"
                : "text-muted hover:text-foreground"
            }`}
          >
            <LayoutGrid className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            Grid
          </button>
        </div>
      </div>

      {showCards ? (
        <div
          className={
            view === "grid" && !isMobile
              ? "grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
              : "grid gap-3"
          }
        >
          {documents.map((doc) => (
            <DocumentCard
              key={doc.id}
              doc={doc}
              currentUser={currentUser}
              mode={mode}
              downloadingId={downloadingId}
              onDownload={onDownload}
              onDelete={onDelete}
            />
          ))}
        </div>
      ) : (
        <div className="tv-table-wrap">
          <table className="tv-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Category</th>
                {mode === "shared" || mode === "all" ? <th>Access</th> : null}
                <th className="hidden sm:table-cell">Type</th>
                <th className="hidden md:table-cell">Updated</th>
                {mode !== "owned" ? (
                  <th className="hidden sm:table-cell">Owner</th>
                ) : null}
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => {
                const isOwner =
                  doc.your_access === "OWNER" ||
                  doc.owner.id === currentUser.id;
                const accessLabel = formatDocumentAccessLabel(doc.your_access);
                return (
                  <tr key={doc.id}>
                    <td className="font-medium text-foreground">
                      <div className="flex items-start gap-2.5">
                        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
                          <FileTypeIcon mime={doc.mime_type} />
                        </span>
                        <div className="min-w-0">
                          <Link
                            href={`/documents/${doc.id}`}
                            className="hover:text-accent-strong"
                          >
                            {doc.title}
                          </Link>
                          <span className="sr-only"> ({accessLabel})</span>
                          <p className="mt-0.5 text-xs text-muted sm:hidden">
                            {mimeLabel(doc.mime_type)} ·{" "}
                            {formatBytes(doc.file_size)}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="text-muted">{doc.category}</td>
                    {mode === "shared" || mode === "all" ? (
                      <td>
                        <AccessBadge level={doc.your_access} />
                      </td>
                    ) : null}
                    <td className="hidden text-muted sm:table-cell">
                      {mimeLabel(doc.mime_type)}
                      <span className="mt-0.5 block text-xs">
                        {formatBytes(doc.file_size)}
                      </span>
                    </td>
                    <td className="hidden text-muted md:table-cell">
                      {formatDateTime(doc.created_at)}
                    </td>
                    {mode !== "owned" ? (
                      <td className="hidden text-muted sm:table-cell">
                        {doc.owner.name}
                        {isOwner ? (
                          <span className="ml-1 text-xs text-accent-strong">
                            (you)
                          </span>
                        ) : null}
                      </td>
                    ) : null}
                    <td className="whitespace-nowrap">
                      <DocumentActions
                        doc={doc}
                        isOwner={isOwner}
                        downloadingId={downloadingId}
                        onDownload={onDownload}
                        onDelete={onDelete}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function PaginationBar({
  page,
  totalPages,
  total,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  if (totalPages <= 0) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius)] border border-border bg-surface px-4 py-3 text-sm shadow-[var(--shadow-sm)]">
      <p className="text-muted">
        <span className="font-medium text-foreground">{total}</span> result
        {total === 1 ? "" : "s"}
        {" · "}
        Page {page} of {totalPages}
      </p>
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
