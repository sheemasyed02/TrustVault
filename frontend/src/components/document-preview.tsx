"use client";

import { FileSearch, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  previewDocumentRequest,
  putDocumentContentRequest,
  type DocumentDetail,
} from "@/lib/api";
import { DOCX_MIME_TYPE, PDF_MIME_TYPE } from "@/lib/upload-rules";

interface DocumentPreviewProps {
  document: DocumentDetail;
  /** Owner or EDIT grantee ? contenteditable + save for DOCX only. */
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
      <section className="rounded-[var(--radius)] border border-border bg-surface p-5 text-sm shadow-[var(--shadow-sm)] sm:p-6">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-strong">
            <FileSearch className="h-5 w-5" strokeWidth={1.75} aria-hidden />
          </span>
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              Preview
            </h2>
            <p className="mt-1 text-muted">
              In-browser preview supports DOCX (and legacy PDF rows). This file
              type ({document.mime_type}) is unsupported ? use Download PDF if
              you still have access.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-[var(--radius)] border border-border bg-surface p-5 shadow-[var(--shadow-sm)] sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-strong">
            <FileSearch className="h-5 w-5" strokeWidth={1.75} aria-hidden />
          </span>
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              {isPdf
                ? "PDF preview (legacy)"
                : canEditDocx
                  ? "Edit document content"
                  : "Document preview"}
            </h2>
            <p className="mt-1 text-sm text-muted">
              {isPdf
                ? "Legacy PDF ? in-app editing is not available."
                : canEditDocx
                  ? "Edit the body below, then save. PDF export uses the latest saved file."
                  : "Read-only preview."}
            </p>
          </div>
        </div>
        {canEditDocx ? (
          <Button
            type="button"
            variant="primary"
            onClick={() => void onSave()}
            disabled={!dirty || saving || status !== "ready"}
          >
            {saving ? (
              <>
                <LoaderCircle
                  className="h-4 w-4 animate-spin"
                  strokeWidth={1.75}
                  aria-hidden
                />
                Saving?
              </>
            ) : (
              "Save content"
            )}
          </Button>
        ) : null}
      </div>

      {status === "loading" || status === "idle" ? (
        <div className="mt-4 space-y-2" role="status" aria-busy>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-[92%]" />
          <Skeleton className="h-4 w-[80%]" />
          <span className="sr-only">Loading document?</span>
        </div>
      ) : null}

      {error ? (
        <div className="mt-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
      {message ? (
        <div className="mt-4">
          <Alert tone="success">{message}</Alert>
        </div>
      ) : null}

      {status === "ready" && isPdf && pdfUrl ? (
        <iframe
          title="PDF preview"
          src={pdfUrl}
          className="mt-4 h-[70vh] w-full rounded-[0.75rem] border border-border bg-white"
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
          className={`docx-preview mt-4 max-h-[70vh] overflow-auto rounded-[0.75rem] border border-border bg-white px-5 py-4 text-sm leading-relaxed text-foreground outline-none ${
            canEditDocx
              ? "focus-visible:ring-2 focus-visible:ring-accent/40"
              : "cursor-default"
          }`}
        />
      ) : null}
    </section>
  );
}
