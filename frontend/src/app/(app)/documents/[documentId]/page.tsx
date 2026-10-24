"use client";

import {
  ArrowLeft,
  Download,
  LoaderCircle,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { DocumentAuditPanel } from "@/components/document-audit-panel";
import { DocumentMetadataForm } from "@/components/document-metadata-form";
import { DocumentPermissionsPanel } from "@/components/document-permissions-panel";
import { DocumentPreview } from "@/components/document-preview";
import { FileTypeIcon } from "@/components/file-type-icon";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
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
        className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent-strong hover:underline"
      >
        <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        Back
      </Link>

      {status === "loading" ? (
        <div role="status" aria-busy="true">
          <Panel className="space-y-4">
            <div className="flex items-start gap-3">
              <Skeleton className="h-12 w-12 rounded-xl" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-7 w-2/3" />
                <Skeleton className="h-4 w-1/3" />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Skeleton className="h-16 w-full rounded-[0.75rem]" />
              <Skeleton className="h-16 w-full rounded-[0.75rem]" />
              <Skeleton className="h-16 w-full rounded-[0.75rem]" />
            </div>
            <span className="sr-only">Loading document…</span>
          </Panel>
        </div>
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
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-strong">
                  <FileTypeIcon mime={doc.mime_type} className="h-6 w-6" />
                </span>
                <div className="min-w-0">
                  <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                    {doc.title}
                  </h1>
                  <p className="mt-1 text-sm text-muted">
                    {access.isOwner
                      ? "You own this document"
                      : `Shared by ${doc.owner.name}`}
                    {" · "}
                    {mimeLabel(doc.mime_type)}
                    {" · "}
                    {formatBytes(doc.file_size)}
                  </p>
                </div>
              </div>
              <Badge
                tone={
                  access.yourAccess === "EDIT" || access.isOwner
                    ? "accent"
                    : "neutral"
                }
              >
                {formatDocumentAccessLabel(access.yourAccess)}
              </Badge>
            </div>

            <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Detail label="Category" value={doc.category} />
              <Detail label="Created" value={formatDateTime(doc.created_at)} />
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
                aria-busy={actions.downloadingId === doc.id}
              >
                {actions.downloadingId === doc.id ? (
                  <>
                    <LoaderCircle
                      className="h-4 w-4 animate-spin"
                      strokeWidth={1.75}
                      aria-hidden
                    />
                    Downloading…
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                    Download PDF
                  </>
                )}
              </Button>
              {access.canDelete ? (
                <Button
                  variant="danger"
                  onClick={() => actions.requestDelete(doc)}
                  disabled={actions.deleting || actions.downloadingId === doc.id}
                >
                  <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  Delete
                </Button>
              ) : null}
            </div>

            {actions.actionError ? (
              <div className="mt-3">
                <Alert tone="error">{actions.actionError}</Alert>
              </div>
            ) : null}
            {actions.actionMessage ? (
              <div className="mt-3">
                <Alert tone="success">{actions.actionMessage}</Alert>
              </div>
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
    <div className="rounded-[0.75rem] border border-border bg-accent-soft/30 px-3 py-2.5">
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm text-foreground">{value}</dd>
    </div>
  );
}
