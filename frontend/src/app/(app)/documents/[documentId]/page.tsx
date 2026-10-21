"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { useDocumentActions } from "@/hooks/use-document-actions";
import {
  ApiError,
  getDocumentRequest,
  type DocumentDetail,
} from "@/lib/api";
import { formatBytes, formatDateTime, mimeLabel } from "@/lib/format";

export default function DocumentDetailPage() {
  const params = useParams<{ documentId: string }>();
  const router = useRouter();
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const actions = useDocumentActions(() => {
    router.push("/documents");
  });

  useEffect(() => {
    if (!accessToken || !params.documentId) return;
    const controller = new AbortController();
    const token = accessToken;
    const documentId = params.documentId;

    void (async () => {
      setStatus("loading");
      setError(null);
      setDoc(null);
      try {
        const data = await getDocumentRequest(token, documentId, controller.signal);
        setDoc(data);
        setStatus("ready");
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setDoc(null);
        setError(err instanceof ApiError ? err.detail : "Unable to load document.");
        setStatus("error");
      }
    })();

    return () => controller.abort();
  }, [accessToken, handleUnauthorized, params.documentId]);

  if (!user) return null;

  const isOwner = doc ? doc.owner.id === user.id : false;

  return (
    <div className="space-y-5">
      <Link
        href="/documents"
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← Back to documents
      </Link>

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading document…
        </p>
      ) : null}

      {status === "error" ? (
        <div role="alert" className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-4 text-sm text-danger">
          {error}
          <p className="mt-2 text-muted">
            No document metadata from the failed response is shown.
          </p>
        </div>
      ) : null}

      {status === "ready" && doc ? (
        <article className="rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow)]">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
            Document details
          </p>
          <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
            {doc.title}
          </h1>
          <p className="mt-2 text-sm text-muted">
            {isOwner ? "You own this document." : `Owned by ${doc.owner.name}.`}
          </p>

          <dl className="mt-6 grid gap-4 sm:grid-cols-2">
            <Detail label="Category" value={doc.category} />
            <Detail label="Type" value={mimeLabel(doc.mime_type)} />
            <Detail label="Size" value={formatBytes(doc.file_size)} />
            <Detail label="Created" value={formatDateTime(doc.created_at)} />
            <Detail label="Updated" value={formatDateTime(doc.updated_at)} />
            <Detail label="Owner email" value={doc.owner.email} />
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
              {actions.downloadingId === doc.id ? "Downloading…" : "Download"}
            </button>
            {isOwner ? (
              <button
                type="button"
                onClick={() => void actions.remove(doc)}
                className="rounded-md border border-danger/40 px-4 py-2 text-sm font-semibold text-danger"
              >
                Delete
              </button>
            ) : null}
          </div>

          <p className="mt-4 text-xs text-muted">
            Edit metadata and permission management forms are not part of this
            task. Those buttons are omitted on purpose.
          </p>

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
      ) : null}
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
