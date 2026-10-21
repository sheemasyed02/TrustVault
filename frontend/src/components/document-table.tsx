"use client";

import Link from "next/link";

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
  const label = formatDocumentAccessLabel(level);
  const tone =
    level === "EDIT"
      ? "bg-accent-soft text-accent-strong"
      : level === "OWNER"
        ? "bg-white text-foreground border border-border"
        : "bg-white text-muted border border-border";
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs font-semibold ${tone}`}
    >
      {level === "OWNER" ? "Owner" : level}
    </span>
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
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-border bg-white/50 text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="px-4 py-3 font-semibold">Title</th>
            <th className="px-4 py-3 font-semibold">Category</th>
            {mode === "shared" || mode === "all" ? (
              <th className="px-4 py-3 font-semibold">Your access</th>
            ) : null}
            <th className="px-4 py-3 font-semibold">Type</th>
            <th className="px-4 py-3 font-semibold">Size</th>
            <th className="px-4 py-3 font-semibold">Created</th>
            {mode !== "owned" ? (
              <th className="px-4 py-3 font-semibold">Owner</th>
            ) : null}
            <th className="px-4 py-3 font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const isOwner =
              doc.your_access === "OWNER" || doc.owner.id === currentUser.id;
            const accessLabel = formatDocumentAccessLabel(doc.your_access);
            return (
              <tr key={doc.id} className="border-b border-border/70 last:border-0">
                <td className="px-4 py-3 font-medium text-foreground">
                  <Link
                    href={`/documents/${doc.id}`}
                    className="hover:text-accent-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    {doc.title}
                  </Link>
                  <span className="sr-only"> ({accessLabel})</span>
                </td>
                <td className="px-4 py-3 text-muted">{doc.category}</td>
                {mode === "shared" || mode === "all" ? (
                  <td className="px-4 py-3">
                    <AccessBadge level={doc.your_access} />
                  </td>
                ) : null}
                <td className="px-4 py-3 text-muted">{mimeLabel(doc.mime_type)}</td>
                <td className="px-4 py-3 text-muted">
                  {formatBytes(doc.file_size)}
                </td>
                <td className="px-4 py-3 text-muted">
                  {formatDateTime(doc.created_at)}
                </td>
                {mode !== "owned" ? (
                  <td className="px-4 py-3 text-muted">
                    {doc.owner.name}
                    {isOwner ? (
                      <span className="ml-1 text-xs text-accent-strong">(you)</span>
                    ) : null}
                  </td>
                ) : null}
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Link
                      href={`/documents/${doc.id}`}
                      className="rounded-md border border-border px-2 py-1 text-xs font-semibold hover:bg-accent-soft"
                    >
                      Open
                    </Link>
                    <button
                      type="button"
                      onClick={() => onDownload(doc)}
                      disabled={downloadingId === doc.id}
                      className="rounded-md border border-border px-2 py-1 text-xs font-semibold hover:bg-accent-soft disabled:opacity-60"
                    >
                      {downloadingId === doc.id ? "Downloading…" : "Download"}
                    </button>
                    {isOwner && onDelete ? (
                      <button
                        type="button"
                        onClick={() => onDelete(doc)}
                        className="rounded-md border border-danger/40 px-2 py-1 text-xs font-semibold text-danger hover:bg-danger/5"
                      >
                        Delete
                      </button>
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
        Server total: <span className="font-medium text-foreground">{total}</span>
        {" · "}
        Page {page} of {totalPages}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded-md border border-border px-3 py-1.5 font-semibold disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="rounded-md border border-border px-3 py-1.5 font-semibold disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
