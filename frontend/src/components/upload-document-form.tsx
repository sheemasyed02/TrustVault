"use client";

import { FileText, LoaderCircle, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useRef, useState, type DragEvent, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { FileTypeIcon } from "@/components/file-type-icon";
import { Alert } from "@/components/ui/alert";
import { Button, buttonClassName } from "@/components/ui/button";
import { ApiError, uploadDocumentRequest } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import {
  DOCX_MIME_TYPE,
  MAX_UPLOAD_BYTES,
  validateUploadFileClient,
} from "@/lib/upload-rules";

type FieldKey = "title" | "category" | "file" | null;

export function UploadDocumentForm() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const categoryId = useId();
  const descriptionId = useId();
  const fileInputId = useId();

  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fieldError, setFieldError] = useState<FieldKey>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  function onFileChange(next: File | null) {
    setFile(next);
    const validation = validateUploadFileClient(next);
    setClientError(validation);
    setFieldError(validation ? "file" : null);
    setServerError(null);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    const next = event.dataTransfer.files?.[0] ?? null;
    onFileChange(next);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || submitting) return;

    const trimmedTitle = title.trim();
    const trimmedCategory = category.trim();
    if (!trimmedTitle) {
      setClientError("Title is required.");
      setFieldError("title");
      return;
    }
    if (!trimmedCategory) {
      setClientError("Category is required.");
      setFieldError("category");
      return;
    }
    const fileError = validateUploadFileClient(file);
    if (fileError || !file) {
      setClientError(fileError ?? "Choose a file to upload.");
      setFieldError("file");
      return;
    }

    setClientError(null);
    setFieldError(null);
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
      className="space-y-5"
      noValidate
    >
      <div
        role="button"
        tabIndex={0}
        aria-controls={fileInputId}
        aria-label="Choose a DOCX file to upload"
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onClick={() => fileInputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setDragOver(false);
        }}
        onDrop={onDrop}
        className={`rounded-[var(--radius)] border-2 border-dashed px-4 py-8 text-center transition-colors duration-[180ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
          dragOver
            ? "border-accent bg-accent-soft"
            : fieldError === "file"
              ? "border-danger/50 bg-[color-mix(in_srgb,var(--danger)_6%,white)]"
              : "border-border bg-accent-soft/50 hover:border-accent/50 hover:bg-accent-soft"
        }`}
      >
        <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-surface text-accent shadow-[var(--shadow-sm)]">
          <Upload className="h-5 w-5" strokeWidth={1.75} aria-hidden />
        </span>
        <p className="mt-3 text-sm font-semibold text-foreground">
          Drop a DOCX file here, or choose a file
        </p>
        <p className="mt-1 text-xs text-muted">
          DOCX only · max {formatBytes(MAX_UPLOAD_BYTES)}. PDF and other formats
          are rejected.
        </p>
        <span className="mt-4 inline-flex">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={(event) => {
              event.stopPropagation();
              fileInputRef.current?.click();
            }}
          >
            Choose file
          </Button>
        </span>
        <label htmlFor={fileInputId} className="sr-only">
          File
        </label>
        <input
          ref={fileInputRef}
          id={fileInputId}
          type="file"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          className="sr-only"
        />
      </div>

      {file ? (
        <div
          data-testid="selected-file"
          className="flex items-start gap-3 rounded-[0.75rem] border border-border bg-surface px-3 py-3"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
            <FileTypeIcon mime={file.type || DOCX_MIME_TYPE} className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">
              {file.name}
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {formatBytes(file.size)}
              {" · "}
              {file.type || DOCX_MIME_TYPE}
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="ml-auto shrink-0"
            disabled={submitting}
            onClick={() => {
              onFileChange(null);
              if (fileInputRef.current) fileInputRef.current.value = "";
            }}
          >
            Remove
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-muted">
          <FileText className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          No file selected yet
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={titleId} className="tv-label">
            Title
          </label>
          <input
            id={titleId}
            required
            maxLength={255}
            value={title}
            disabled={submitting}
            aria-invalid={fieldError === "title" || undefined}
            onChange={(event) => {
              setTitle(event.target.value);
              if (fieldError === "title") {
                setFieldError(null);
                setClientError(null);
              }
            }}
            className={`tv-input ${
              fieldError === "title" ? "border-danger focus:border-danger" : ""
            }`}
          />
        </div>
        <div>
          <label htmlFor={categoryId} className="tv-label">
            Category
          </label>
          <input
            id={categoryId}
            required
            maxLength={128}
            value={category}
            disabled={submitting}
            aria-invalid={fieldError === "category" || undefined}
            onChange={(event) => {
              setCategory(event.target.value);
              if (fieldError === "category") {
                setFieldError(null);
                setClientError(null);
              }
            }}
            className={`tv-input ${
              fieldError === "category" ? "border-danger focus:border-danger" : ""
            }`}
          />
        </div>
      </div>

      <div>
        <label htmlFor={descriptionId} className="tv-label">
          Description (optional)
        </label>
        <textarea
          id={descriptionId}
          maxLength={5000}
          rows={3}
          value={description}
          disabled={submitting}
          onChange={(event) => setDescription(event.target.value)}
          className="tv-input"
        />
      </div>

      {clientError ? (
        <Alert tone="error">{clientError}</Alert>
      ) : null}
      {serverError ? (
        <p
          role="alert"
          className="rounded-[var(--radius)] border border-danger/30 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-4 py-3 text-sm text-danger"
          data-testid="upload-error"
        >
          {serverError}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button type="submit" variant="primary" disabled={submitting} aria-busy={submitting}>
          {submitting ? (
            <>
              <LoaderCircle
                className="h-4 w-4 animate-spin"
                strokeWidth={1.75}
                aria-hidden
              />
              Uploading…
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              Upload document
            </>
          )}
        </Button>
        <Link
          href="/documents"
          className={buttonClassName({
            variant: "secondary",
            className: submitting ? "pointer-events-none opacity-60" : "",
          })}
          aria-disabled={submitting}
          tabIndex={submitting ? -1 : undefined}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
