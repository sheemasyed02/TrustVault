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
        // Clear protected content immediately when access is denied/revoked.
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
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-4 text-sm text-danger"
        >
          <p>{error}</p>
          <p className="mt-2 text-muted">
            {errorStatus === 404
              ? "The document is missing, deleted, or you do not have access. No private metadata is shown."
              : "No document metadata from the failed response is shown."}
          </p>
        </div>
      ) : null}

      {status === "ready" && doc && access ? (
        <>
          <article className="rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow)]">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
              Document details
            </p>
            <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
              {doc.title}
            </h1>
            <p className="mt-2 text-sm text-muted">
              {access.isOwner
                ? "You own this document — you can view, edit content and metadata, share, and delete."
                : access.yourAccess === "EDIT"
                  ? `Shared by ${doc.owner.name} with EDIT access — you can view and edit document contents. Metadata, sharing, and delete remain owner-only.`
                  : `Shared by ${doc.owner.name} with READ access — view and download only.`}
            </p>
            <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-accent-strong">
              Document access: {formatDocumentAccessLabel(access.yourAccess)}
              <span className="mt-1 block normal-case tracking-normal text-muted">
                Separate from your platform role ({user.role}). Sharing never
                changes ADMIN / OWNER / VIEWER.
              </span>
            </p>

            <dl className="mt-6 grid gap-4 sm:grid-cols-2">
              <Detail
                label="Original filename"
                value={
                  doc.original_filename?.trim()
                    ? doc.original_filename
                    : "—"
                }
              />
              <Detail label="Category" value={doc.category} />
              <Detail label="Type" value={mimeLabel(doc.mime_type)} />
              <Detail label="Size" value={formatBytes(doc.file_size)} />
              <Detail label="Created" value={formatDateTime(doc.created_at)} />
              <Detail label="Updated" value={formatDateTime(doc.updated_at)} />
              <Detail label="Owner" value={`${doc.owner.name} (${doc.owner.email})`} />
              <Detail label="Checksum" value={doc.sha256_checksum} />
              <Detail
                label="Description"
                value={doc.description?.trim() ? doc.description : "—"}
              />
            </dl>

            <div className="mt-6 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void actions.download(doc)}
                disabled={actions.downloadingId === doc.id}
                className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
              >
                {actions.downloadingId === doc.id
                  ? "Downloading…"
                  : "Download PDF"}
              </button>
              {access.canDelete ? (
                <button
                  type="button"
                  onClick={() => actions.requestDelete(doc)}
                  className="rounded-md border border-danger/40 px-4 py-2 text-sm font-semibold text-danger"
                >
                  Delete
                </button>
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
          </article>

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
          ) : (
            <section className="rounded-xl border border-border bg-surface p-5 text-sm text-muted">
              <h2 className="font-display text-xl text-foreground">Metadata</h2>
              <p className="mt-2">
                Only the document owner can change title, category, or
                description.
              </p>
            </section>
          )}

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
      <dd className="mt-1 break-all text-sm text-foreground">{value}</dd>
    </div>
  );
}
