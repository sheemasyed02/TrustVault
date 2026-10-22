"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  previewDocumentRequest,
  putDocumentContentRequest,
  type DocumentDetail,
} from "@/lib/api";
import { DOCX_MIME_TYPE, PDF_MIME_TYPE } from "@/lib/upload-rules";

interface DocumentPreviewProps {
  document: DocumentDetail;
  /** Owner or EDIT grantee — contenteditable + save for DOCX only. */
  canEdit: boolean;
  onDocumentUpdated?: (next: DocumentDetail) => void;
}

/**
 * Authorized in-browser preview/editor.
 *
 * - DOCX: mammoth HTML preview; owners/EDIT may edit plain text and save.
 *   Saves rewrite the document body while preserving other DOCX package parts
 *   when possible (styles/media/headers). Body tables/images are simplified.
 * - Legacy PDF rows: native browser preview only (new uploads are DOCX-only).
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
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const isDocx = document.mime_type === DOCX_MIME_TYPE;
  const isPdf = document.mime_type === PDF_MIME_TYPE;
  const supported = isDocx || isPdf;
  const canEditDocx = canEdit && isDocx;

  useEffect(() => {
    if (!accessToken || !supported) return;
    const controller = new AbortController();
    let cancelled = false;
    let objectUrl: string | null = null;

    void (async () => {
      setStatus("loading");
      setError(null);
      setMessage(null);
      setHtml(null);
      setPdfUrl(null);
      setDirty(false);
      try {
        const result = await previewDocumentRequest(
          accessToken,
          document.id,
          controller.signal,
        );
        if (cancelled) return;
        const buffer = await result.blob.arrayBuffer();

        if (isDocx) {
          const mammothMod = await import("mammoth");
          const mammoth = mammothMod.default ?? mammothMod;
          const converted = await mammoth.convertToHtml({ arrayBuffer: buffer });
          if (cancelled) return;
          setHtml(converted.value);
          setStatus("ready");
          return;
        }

        const blob = new Blob([buffer], { type: PDF_MIME_TYPE });
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setPdfUrl(objectUrl);
        setStatus("ready");
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (cancelled) return;
        if (handleUnauthorized(err)) return;
        setHtml(null);
        setPdfUrl(null);
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
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [
    accessToken,
    document.id,
    document.sha256_checksum,
    handleUnauthorized,
    isDocx,
    supported,
  ]);

  useEffect(() => {
    if (status !== "ready" || !editorRef.current || html === null || !isDocx)
      return;
    editorRef.current.innerHTML = html;
  }, [html, status, isDocx]);

  async function onSave() {
    if (!accessToken || !canEditDocx || !editorRef.current || saving) return;
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
      setMessage("Content saved. Download PDF uses the latest saved DOCX.");
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(
        err instanceof ApiError ? err.detail : "Failed to save document content.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!supported) {
    return (
      <section className="rounded-xl border border-border bg-surface p-5 text-sm text-muted shadow-[var(--shadow)]">
        <h2 className="font-display text-xl text-foreground">Preview</h2>
        <p className="mt-2">
          In-browser preview supports DOCX (and legacy PDF rows). This file type
          ({document.mime_type}) is unsupported — use Download PDF if you still
          have access.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl text-foreground">
            {isPdf
              ? "PDF preview (legacy)"
              : canEditDocx
                ? "Edit document content"
                : "Document preview"}
          </h2>
          <p className="mt-1 text-sm text-muted">
            {isPdf
              ? "Legacy PDF — in-app editing is not available."
              : canEditDocx
                ? "Edit the body below, then save. PDF export uses the latest saved file."
                : "Read-only preview."}
          </p>
        </div>
        {canEditDocx ? (
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={!dirty || saving || status !== "ready"}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
          >
            {saving ? "Saving…" : "Save content"}
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

      {status === "ready" && isPdf && pdfUrl ? (
        <iframe
          title="PDF preview"
          src={pdfUrl}
          className="mt-4 h-[70vh] w-full rounded-md border border-border bg-white"
        />
      ) : null}

      {status === "ready" && isDocx ? (
        <div
          ref={editorRef}
          role={canEditDocx ? "textbox" : undefined}
          aria-label={canEditDocx ? "Editable document body" : "Document body"}
          aria-readonly={!canEditDocx}
          contentEditable={canEditDocx}
          suppressContentEditableWarning
          onInput={() => {
            if (canEditDocx) setDirty(true);
          }}
          className={`docx-preview mt-4 max-h-[70vh] overflow-auto rounded-md border border-border bg-white px-5 py-4 text-sm leading-relaxed text-foreground outline-none ${
            canEditDocx
              ? "focus-visible:ring-2 focus-visible:ring-accent/40"
              : "cursor-default"
          }`}
        />
      ) : null}
    </section>
  );
}
