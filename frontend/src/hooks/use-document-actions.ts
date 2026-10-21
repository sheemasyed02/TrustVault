"use client";

import { useCallback, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  deleteDocumentRequest,
  downloadDocumentRequest,
  resolveDownloadFilename,
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
  const [deleting, setDeleting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Pick<
    DocumentListItem,
    "id" | "title"
  > | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const download = useCallback(
    async (
      doc: Pick<DocumentListItem, "id" | "title"> &
        Partial<Pick<DocumentListItem, "mime_type" | "original_filename">>,
    ) => {
      if (!accessToken) return;
      setActionError(null);
      setActionMessage(null);
      setDownloadingId(doc.id);
      try {
        const result = await downloadDocumentRequest(accessToken, doc.id);
        const filename = resolveDownloadFilename({
          headerFilename: result.filename,
          fallbackTitle: doc.title,
          originalFilename: doc.original_filename,
          contentType: result.contentType || doc.mime_type,
        });
        triggerBrowserDownload(result.blob, filename);
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

  const requestDelete = useCallback((doc: Pick<DocumentListItem, "id" | "title">) => {
    setActionError(null);
    setActionMessage(null);
    setPendingDelete(doc);
  }, []);

  const cancelDelete = useCallback(() => {
    if (!deleting) setPendingDelete(null);
  }, [deleting]);

  const confirmDelete = useCallback(async () => {
    if (!accessToken || !pendingDelete || deleting) return;
    setDeleting(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const result = await deleteDocumentRequest(accessToken, pendingDelete.id);
      if (result.storage_cleanup === "completed" || result.storage_cleanup === "already_absent") {
        setActionMessage(
          result.storage_cleanup === "completed"
            ? "Document deleted."
            : "Document deleted (storage object was already absent).",
        );
        setPendingDelete(null);
        onDeleted?.();
      } else {
        setActionError("Delete response was incomplete.");
      }
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setActionError(
        error instanceof ApiError ? error.detail : "Delete failed.",
      );
      setPendingDelete(null);
    } finally {
      setDeleting(false);
    }
  }, [accessToken, deleting, handleUnauthorized, onDeleted, pendingDelete]);

  return {
    download,
    requestDelete,
    confirmDelete,
    cancelDelete,
    pendingDelete,
    deleting,
    downloadingId,
    actionError,
    actionMessage,
    clearActionFeedback: () => {
      setActionError(null);
      setActionMessage(null);
    },
  };
}
