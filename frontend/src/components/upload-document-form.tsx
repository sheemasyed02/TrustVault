"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ApiError, uploadDocumentRequest } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import {
  MAX_UPLOAD_BYTES,
  validateUploadFileClient,
} from "@/lib/upload-rules";

export function UploadDocumentForm() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const router = useRouter();

  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function onFileChange(next: File | null) {
    setFile(next);
    setClientError(validateUploadFileClient(next));
    setServerError(null);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || submitting) return;

    const trimmedTitle = title.trim();
    const trimmedCategory = category.trim();
    if (!trimmedTitle) {
      setClientError("Title is required.");
      return;
    }
    if (!trimmedCategory) {
      setClientError("Category is required.");
      return;
    }
    const fileError = validateUploadFileClient(file);
    if (fileError || !file) {
      setClientError(fileError ?? "Choose a file to upload.");
      return;
    }

    setClientError(null);
    setServerError(null);
    setSubmitting(true);
    try {
      const created = await uploadDocumentRequest(accessToken, {
        title: trimmedTitle,
        category: trimmedCategory,
        description: description.trim() || undefined,
        file,
      });
      router.push(`/documents/${created.id}`);
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setServerError(
        error instanceof ApiError
          ? error.detail
          : "Upload failed. The document was not created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void onSubmit(event)}
      className="space-y-4 rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]"
      noValidate
    >
      <p className="text-sm text-muted">
        Allowed type: Microsoft Word DOCX only. PDF, legacy Word (.doc), and
        other formats are rejected. Maximum size {formatBytes(MAX_UPLOAD_BYTES)}{" "}
        ({MAX_UPLOAD_BYTES.toLocaleString()} bytes). Client checks are guidance
        only — the server validates extension, MIME type, and DOCX structure.
      </p>

      <label className="block text-sm">
        <span className="mb-1 block font-medium">Title</span>
        <input
          required
          maxLength={255}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        />
      </label>

      <label className="block text-sm">
        <span className="mb-1 block font-medium">Category</span>
        <input
          required
          maxLength={128}
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        />
      </label>

      <label className="block text-sm">
        <span className="mb-1 block font-medium">Description (optional)</span>
        <textarea
          maxLength={5000}
          rows={3}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        />
      </label>

      <label className="block text-sm">
        <span className="mb-1 block font-medium">File</span>
        <input
          type="file"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          className="block w-full text-sm"
        />
      </label>

      {file ? (
        <p className="text-sm text-muted" data-testid="selected-file">
          Selected: {file.name} · {formatBytes(file.size)}
        </p>
      ) : null}

      {clientError ? (
        <p role="alert" className="text-sm text-danger">
          {clientError}
        </p>
      ) : null}
      {serverError ? (
        <p role="alert" className="text-sm text-danger" data-testid="upload-error">
          {serverError}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
      >
        {submitting ? "Uploading…" : "Upload document"}
      </button>
    </form>
  );
}
