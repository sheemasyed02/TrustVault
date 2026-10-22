"use client";

import { useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  patchDocumentRequest,
  type DocumentDetail,
} from "@/lib/api";

interface DocumentMetadataFormProps {
  document: DocumentDetail;
  /** When false, the form is not shown (e.g. simulated READ-only UI). */
  canEdit: boolean;
  onUpdated: (next: DocumentDetail) => void;
  onEditDenied?: (message: string) => void;
}

export function DocumentMetadataForm({
  document,
  canEdit,
  onUpdated,
  onEditDenied,
}: DocumentMetadataFormProps) {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [title, setTitle] = useState(document.title);
  const [category, setCategory] = useState(document.category);
  const [description, setDescription] = useState(document.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!canEdit) return null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || submitting) return;

    const trimmedTitle = title.trim();
    const trimmedCategory = category.trim();
    if (!trimmedTitle || !trimmedCategory) {
      setError("Title and category are required.");
      return;
    }

    setError(null);
    setMessage(null);
    setSubmitting(true);
    try {
      const updated = await patchDocumentRequest(accessToken, document.id, {
        title: trimmedTitle,
        category: trimmedCategory,
        description: description.trim() ? description.trim() : null,
      });
      onUpdated(updated);
      setTitle(updated.title);
      setCategory(updated.category);
      setDescription(updated.description ?? "");
      setMessage("Metadata updated.");
    } catch (err) {
      if (handleUnauthorized(err)) return;
      const detail =
        err instanceof ApiError ? err.detail : "Metadata update failed.";
      setError(detail);
      if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
        onEditDenied?.(detail);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section
      aria-label="Edit metadata"
      className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]"
    >
      <h2 className="font-display text-xl text-foreground">Edit details</h2>
      <p className="mt-1 text-sm text-muted">
        Owner-only title, category, and description. Document body editing is
        separate.
      </p>
      <p className="mt-1 text-sm text-muted">
        Only title, category, and description can be changed. Owner and EDIT
        grantees may save; READ grants are rejected by the server.
      </p>

      <form
        onSubmit={(event) => void onSubmit(event)}
        className="mt-4 space-y-3"
        noValidate
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Title</span>
          <input
            value={title}
            maxLength={255}
            onChange={(event) => setTitle(event.target.value)}
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Category</span>
          <input
            value={category}
            maxLength={128}
            onChange={(event) => setCategory(event.target.value)}
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Description</span>
          <textarea
            value={description}
            maxLength={5000}
            rows={3}
            onChange={(event) => setDescription(event.target.value)}
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          />
        </label>

        {error ? (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}
        {message ? (
          <p role="status" className="text-sm text-accent-strong">
            {message}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
        >
          {submitting ? "Saving…" : "Save changes"}
        </button>
      </form>
    </section>
  );
}
