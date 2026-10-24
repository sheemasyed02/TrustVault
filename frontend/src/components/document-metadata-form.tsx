"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
  const titleId = useId();
  const categoryId = useId();
  const descriptionId = useId();
  const [title, setTitle] = useState(document.title);
  const [category, setCategory] = useState(document.category);
  const [description, setDescription] = useState(document.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setTitle(document.title);
    setCategory(document.category);
    setDescription(document.description ?? "");
  }, [document.id, document.title, document.category, document.description]);

  if (!canEdit) return null;

  const dirty =
    title.trim() !== document.title ||
    category.trim() !== document.category ||
    (description.trim() || "") !== (document.description?.trim() || "");

  function onCancel() {
    setTitle(document.title);
    setCategory(document.category);
    setDescription(document.description ?? "");
    setError(null);
    setMessage(null);
  }

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
      className="rounded-[var(--radius)] border border-border bg-surface p-5 shadow-[var(--shadow-sm)] sm:p-6"
    >
      <h2 className="text-lg font-semibold tracking-tight text-foreground">
        Edit details
      </h2>
      <p className="mt-1 text-sm text-muted">
        Update title, category, and description only. This does not change the
        file contents.
      </p>

      <form
        onSubmit={(event) => void onSubmit(event)}
        className="mt-4 space-y-3"
        noValidate
      >
        <div>
          <label htmlFor={titleId} className="tv-label">
            Title
          </label>
          <input
            id={titleId}
            className="tv-input"
            value={title}
            maxLength={255}
            disabled={submitting}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={categoryId} className="tv-label">
            Category
          </label>
          <input
            id={categoryId}
            className="tv-input"
            value={category}
            maxLength={128}
            disabled={submitting}
            onChange={(event) => setCategory(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={descriptionId} className="tv-label">
            Description
          </label>
          <textarea
            id={descriptionId}
            className="tv-input"
            value={description}
            maxLength={5000}
            rows={3}
            disabled={submitting}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        {error ? <Alert tone="error">{error}</Alert> : null}
        {message ? <Alert tone="success">{message}</Alert> : null}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button type="submit" variant="primary" disabled={submitting || !dirty}>
            {submitting ? (
              <>
                <LoaderCircle
                  className="h-4 w-4 animate-spin"
                  strokeWidth={1.75}
                  aria-hidden
                />
                Saving…
              </>
            ) : (
              "Save changes"
            )}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={submitting || !dirty}
            onClick={onCancel}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
