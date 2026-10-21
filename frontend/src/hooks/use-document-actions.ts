"use client";

import { useCallback, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  deleteDocumentRequest,
  downloadDocumentRequest,
  type DocumentListItem,
} from "@/lib/api";

function triggerBrowserDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function useDocumentActions(onDeleted?: () => void) {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const download = useCallback(
    async (doc: Pick<DocumentListItem, "id" | "title">) => {
      if (!accessToken) return;
      setActionError(null);
      setActionMessage(null);
      setDownloadingId(doc.id);
      try {
        const result = await downloadDocumentRequest(accessToken, doc.id);
        triggerBrowserDownload(
          result.blob,
          result.filename || `${doc.title || "document"}.bin`,
        );
        setActionMessage("Download started.");
      } catch (error) {
        if (handleUnauthorized(error)) return;
        setActionError(
          error instanceof ApiError ? error.detail : "Download failed.",
        );
      } finally {
        setDownloadingId(null);
      }
    },
    [accessToken, handleUnauthorized],
  );

  const remove = useCallback(
    async (doc: Pick<DocumentListItem, "id" | "title">) => {
      if (!accessToken) return;
      const confirmed = window.confirm(
        `Delete “${doc.title}”? This soft-deletes the document and removes it from lists.`,
      );
      if (!confirmed) return;
      setActionError(null);
      setActionMessage(null);
      try {
        const result = await deleteDocumentRequest(accessToken, doc.id);
        setActionMessage(
          result.storage_cleanup === "completed"
            ? "Document deleted."
            : "Document deleted (storage object was already absent).",
        );
        onDeleted?.();
      } catch (error) {
        if (handleUnauthorized(error)) return;
        setActionError(
          error instanceof ApiError ? error.detail : "Delete failed.",
        );
      }
    },
    [accessToken, handleUnauthorized, onDeleted],
  );

  return {
    download,
    remove,
    downloadingId,
    actionError,
    actionMessage,
    clearActionFeedback: () => {
      setActionError(null);
      setActionMessage(null);
    },
  };
}
