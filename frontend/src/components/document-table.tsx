"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DocumentAccessLevel, DocumentListItem, UserPublic } from "@/lib/api";
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
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={index}
          className="h-14 animate-pulse rounded-lg bg-border/50"
        />
      ))}
    </div>
  );
}

function AccessBadge({ level }: { level: DocumentAccessLevel }) {
  const tone =
    level === "EDIT" || level === "OWNER" ? ("accent" as const) : ("neutral" as const);
  return <Badge tone={tone}>{formatDocumentAccessLabel(level)}</Badge>;
}

export function DocumentTable({
  documents,
  currentUser,
  onDownload,
  onDelete,
  downloadingId,
  mode,
}: DocumentTableProps) {
  return (
    <div className="tv-table-wrap">
      <table className="tv-table">
        <thead>
          <tr>
            <th>Title</th>
            <th>Category</th>
            {mode === "shared" || mode === "all" ? <th>Access</th> : null}
            <th className="hidden sm:table-cell">Type</th>
            <th className="hidden md:table-cell">Updated</th>
            {mode !== "owned" ? <th className="hidden sm:table-cell">Owner</th> : null}
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const isOwner =
              doc.your_access === "OWNER" || doc.owner.id === currentUser.id;
            const accessLabel = formatDocumentAccessLabel(doc.your_access);
            return (
              <tr key={doc.id}>
                <td className="font-medium text-foreground">
                  <Link
                    href={`/documents/${doc.id}`}
                    className="hover:text-accent-strong"
                  >
                    {doc.title}
                  </Link>
                  <span className="sr-only"> ({accessLabel})</span>
                  <p className="mt-0.5 text-xs text-muted sm:hidden">
                    {mimeLabel(doc.mime_type)} · {formatBytes(doc.file_size)}
                  </p>
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
                      <span className="ml-1 text-xs text-accent-strong">(you)</span>
                    ) : null}
                  </td>
                ) : null}
                <td>
                  <div className="flex flex-wrap gap-1.5">
                    <Link
                      href={`/documents/${doc.id}`}
                      className="inline-flex items-center justify-center rounded-md border border-border bg-white px-2.5 py-1.5 text-xs font-semibold hover:bg-accent-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    >
                      Open
                    </Link>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onDownload(doc)}
                      disabled={downloadingId === doc.id}
                    >
                      {downloadingId === doc.id ? "…" : "PDF"}
                    </Button>
                    {isOwner && onDelete ? (
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() => onDelete(doc)}
                      >
                        Delete
                      </Button>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
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
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
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
