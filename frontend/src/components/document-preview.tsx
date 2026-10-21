"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  previewDocumentRequest,
  putDocumentContentRequest,
  type DocumentDetail,
} from "@/lib/api";
import { DOCX_MIME_TYPE } from "@/lib/upload-rules";

interface DocumentPreviewProps {
  document: DocumentDetail;
  /** Owner or EDIT grantee — contenteditable + save. READ is view-only. */
  canEdit: boolean;
  onDocumentUpdated?: (next: DocumentDetail) => void;
}

/**
 * In-browser DOCX viewer/editor.
 * Loads bytes via the authorized API. Owners and EDIT grantees can edit text
 * and save (rebuilds DOCX server-side). READ grantees get a read-only view.
 */
export function DocumentPreview({
  document,
  canEdit,
  onDocumentUpdated,
}: DocumentPreviewProps) {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const editorRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const isDocx = document.mime_type === DOCX_MIME_TYPE;

  useEffect(() => {
    if (!accessToken || !isDocx) return;
    const controller = new AbortController();
    let cancelled = false;

    void (async () => {
      setStatus("loading");
      setError(null);
      setMessage(null);
      setHtml(null);
      setDirty(false);
      try {
        const result = await previewDocumentRequest(
          accessToken,
          document.id,
          controller.signal,
        );
        if (cancelled) return;
        const buffer = await result.blob.arrayBuffer();
        const mammothMod = await import("mammoth");
        const mammoth = mammothMod.default ?? mammothMod;
        const converted = await mammoth.convertToHtml({ arrayBuffer: buffer });
        if (cancelled) return;
        setHtml(converted.value);
        setStatus("ready");
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (cancelled) return;
        if (handleUnauthorized(err)) return;
        setHtml(null);
        setError(
          err instanceof ApiError
            ? err.detail
            : "Unable to load document preview.",
        );
        setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [accessToken, document.id, document.sha256_checksum, handleUnauthorized, isDocx]);

  useEffect(() => {
    if (status !== "ready" || !editorRef.current || html === null) return;
    editorRef.current.innerHTML = html;
  }, [html, status, canEdit]);

  async function onSave() {
    if (!accessToken || !canEdit || !editorRef.current || saving) return;
    const text = editorRef.current.innerText ?? "";
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await putDocumentContentRequest(accessToken, document.id, {
        text,
      });
      onDocumentUpdated?.(updated);
      setDirty(false);
      setMessage("Document content saved.");
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(
        err instanceof ApiError ? err.detail : "Failed to save document content.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!isDocx) {
    return (
      <section className="rounded-xl border border-border bg-surface p-5 text-sm text-muted shadow-[var(--shadow)]">
        <h2 className="font-display text-xl text-foreground">Preview</h2>
        <p className="mt-2">
          In-browser preview is available for DOCX documents. This file type (
          {document.mime_type}) is legacy — use Download if you still have
          access.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl text-foreground">
            {canEdit ? "Document editor" : "Document preview"}
          </h2>
          <p className="mt-1 text-sm text-muted">
            {canEdit
              ? "You can edit this document in TrustVault. Saving rebuilds the stored DOCX (simple text formatting). Use Download for full Word features."
              : "Read-only view. You have READ access — request EDIT from the owner to change content or metadata."}
          </p>
        </div>
        {canEdit ? (
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={!dirty || saving || status !== "ready"}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
          >
            {saving ? "Saving…" : "Save document"}
          </button>
        ) : null}
      </div>

      {status === "loading" || status === "idle" ? (
        <p className="mt-4 text-sm text-muted" role="status">
          Loading document…
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="mt-4 text-sm text-danger">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="mt-4 text-sm text-accent-strong">
          {message}
        </p>
      ) : null}

      {status === "ready" ? (
        <div
          ref={editorRef}
          role={canEdit ? "textbox" : undefined}
          aria-label={canEdit ? "Editable document body" : "Document body"}
          aria-readonly={!canEdit}
          contentEditable={canEdit}
          suppressContentEditableWarning
          onInput={() => {
            if (canEdit) setDirty(true);
          }}
          className={`docx-preview mt-4 max-h-[70vh] overflow-auto rounded-md border border-border bg-white px-5 py-4 text-sm leading-relaxed text-foreground outline-none ${
            canEdit
              ? "focus-visible:ring-2 focus-visible:ring-accent/40"
              : "cursor-default"
          }`}
        />
      ) : null}
    </section>
  );
}
