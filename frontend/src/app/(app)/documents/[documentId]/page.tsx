"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { DocumentAuditPanel } from "@/components/document-audit-panel";
import { DocumentMetadataForm } from "@/components/document-metadata-form";
import { DocumentPermissionsPanel } from "@/components/document-permissions-panel";
import { DocumentPreview } from "@/components/document-preview";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { useDocumentActions } from "@/hooks/use-document-actions";
import {
  ApiError,
  getDocumentRequest,
  type DocumentDetail,
} from "@/lib/api";
import {
  formatDocumentAccessLabel,
  getDocumentUiAccess,
} from "@/lib/document-access";
import { formatBytes, formatDateTime, mimeLabel } from "@/lib/format";

export default function DocumentDetailPage() {
  const params = useParams<{ documentId: string }>();
  const router = useRouter();
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);

  const actions = useDocumentActions(() => {
    router.push("/documents");
  });

  useEffect(() => {
    if (!accessToken || !params.documentId) return;
    let controller = new AbortController();
    const token = accessToken;
    const documentId = params.documentId;

    async function load(showLoading: boolean) {
      if (showLoading) {
        setStatus("loading");
        setError(null);
        setErrorStatus(null);
        setDoc(null);
      }
      try {
        const data = await getDocumentRequest(
          token,
          documentId,
          controller.signal,
        );
        setDoc(data);
        setStatus("ready");
        setError(null);
        setErrorStatus(null);
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setDoc(null);
        if (err instanceof ApiError) {
          setError(err.detail);
          setErrorStatus(err.status);
        } else {
          setError("Unable to load document.");
          setErrorStatus(null);
        }
        setStatus("error");
      }
    }

    void load(true);

    function onVisible() {
      if (document.visibilityState !== "visible") return;
      controller.abort();
      controller = new AbortController();
      void load(false);
    }
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      controller.abort();
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [accessToken, handleUnauthorized, params.documentId]);

  if (!user) return null;

  const access = doc ? getDocumentUiAccess(user, doc) : null;
  const backHref =
    user.role === "VIEWER"
      ? "/shared"
      : access && !access.isOwner
        ? "/shared"
        : "/documents";

  return (
    <div className="space-y-5">
      <Link
        href={backHref}
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← Back
      </Link>

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading document…
        </p>
      ) : null}

      {status === "error" ? (
        <Alert tone="error" title="Unable to open document">
          <p>{error}</p>
          <p className="mt-1 text-muted">
            {errorStatus === 404
              ? "The document is missing, deleted, or you do not have access."
              : "No private metadata from the failed response is shown."}
          </p>
        </Alert>
      ) : null}

      {status === "ready" && doc && access ? (
        <>
          <Panel>
            <PageHeader
              title={doc.title}
              description={
                access.isOwner
                  ? null
                  : `Shared by ${doc.owner.name}`
              }
              actions={
                <Badge
                  tone={
                    access.yourAccess === "EDIT" || access.isOwner
                      ? "accent"
                      : "neutral"
                  }
                >
                  {formatDocumentAccessLabel(access.yourAccess)}
                </Badge>
              }
            />

            <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Detail label="Category" value={doc.category} />
              <Detail label="Type" value={mimeLabel(doc.mime_type)} />
              <Detail label="Size" value={formatBytes(doc.file_size)} />
              <Detail label="Updated" value={formatDateTime(doc.updated_at)} />
              <Detail
                label="Owner"
                value={`${doc.owner.name} (${doc.owner.email})`}
              />
              {doc.original_filename?.trim() ? (
                <Detail label="Filename" value={doc.original_filename} />
              ) : null}
              {doc.description?.trim() ? (
                <Detail label="Description" value={doc.description} />
              ) : null}
            </dl>

            <div className="mt-5 flex flex-wrap gap-2">
              <Button
                variant="primary"
                onClick={() => void actions.download(doc)}
                disabled={actions.downloadingId === doc.id}
              >
                {actions.downloadingId === doc.id
                  ? "Downloading…"
                  : "Download PDF"}
              </Button>
              {access.canDelete ? (
                <Button
                  variant="danger"
                  onClick={() => actions.requestDelete(doc)}
                >
                  Delete
                </Button>
              ) : null}
            </div>

            {actions.actionError ? (
              <p role="alert" className="mt-3 text-sm text-danger">
                {actions.actionError}
              </p>
            ) : null}
            {actions.actionMessage ? (
              <p role="status" className="mt-3 text-sm text-accent-strong">
                {actions.actionMessage}
              </p>
            ) : null}
          </Panel>

          <DocumentPreview
            document={doc}
            canEdit={access.canEditContent}
            onDocumentUpdated={setDoc}
          />

          {access.canEditMetadata ? (
            <DocumentMetadataForm
              document={doc}
              canEdit
              onUpdated={setDoc}
            />
          ) : null}

          <DocumentPermissionsPanel
            documentId={doc.id}
            canManage={access.canManageSharing}
            ownerUserId={doc.owner.id}
          />

          {access.isOwner ? (
            <DocumentAuditPanel documentId={doc.id} />
          ) : null}
        </>
      ) : null}

      <ConfirmDialog
        open={actions.pendingDelete !== null}
        title="Delete this document?"
        description="Deleting removes the document from normal access (soft-delete) and attempts to remove the private storage object. This cannot be undone from the UI."
        confirmLabel="Delete document"
        danger
        busy={actions.deleting}
        onCancel={actions.cancelDelete}
        onConfirm={() => void actions.confirmDelete()}
      />
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 break-words text-sm text-foreground">{value}</dd>
    </div>
  );
}
