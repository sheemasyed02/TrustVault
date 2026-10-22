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
      className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow-sm)]"
    >
      <h2 className="font-display text-xl text-foreground">Edit details</h2>
      <p className="mt-1 text-sm text-muted">
        Update the title, category, and description. Content editing is separate.
      </p>

      <form
        onSubmit={(event) => void onSubmit(event)}
        className="mt-4 space-y-3"
        noValidate
      >
        <label className="block text-sm">
          <span className="tv-label">Title</span>
          <input
            className="tv-input"
            value={title}
            maxLength={255}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="tv-label">Category</span>
          <input
            className="tv-input"
            value={category}
            maxLength={128}
            onChange={(event) => setCategory(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="tv-label">Description</span>
          <textarea
            className="tv-input"
            value={description}
            maxLength={5000}
            rows={3}
            onChange={(event) => setDescription(event.target.value)}
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
          className="inline-flex items-center rounded-md bg-accent px-3.5 py-2 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
        >
          {submitting ? "Saving…" : "Save changes"}
        </button>
      </form>
    </section>
  );
}
