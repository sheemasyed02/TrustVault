"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listDocumentAuditRequest,
  type AuditEventItem,
  type DocumentAuditSummary,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface DocumentAuditPanelProps {
  documentId: string;
}

function viewerLabel(event: AuditEventItem): string {
  const metaRole =
    typeof event.metadata?.actor_role === "string"
      ? event.metadata.actor_role
      : null;
  const name =
    event.actor_name ||
    (typeof event.metadata?.actor_name === "string"
      ? event.metadata.actor_name
      : null);
  const email =
    event.actor_email ||
    (typeof event.metadata?.actor_email === "string"
      ? event.metadata.actor_email
      : null);
  const who = email
    ? name
      ? `${name} <${email}>`
      : email
    : (event.actor_id ?? "Unknown viewer");
  return metaRole ? `${who} · ${metaRole}` : who;
}

/** Owner-only document activity with authorised view history as the primary focus. */
export function DocumentAuditPanel({ documentId }: DocumentAuditPanelProps) {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [summary, setSummary] = useState<DocumentAuditSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [showViewsOnly, setShowViewsOnly] = useState(true);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listDocumentAuditRequest(
          accessToken,
          documentId,
          {
            page_size: 50,
            action: showViewsOnly ? "DOCUMENT_VIEW" : undefined,
          },
          signal,
        );
        setEvents(data.results);
        setSummary(data.summary ?? null);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setError(
          err instanceof ApiError ? err.detail : "Unable to load document activity.",
        );
        setStatus("error");
      }
    },
    [accessToken, documentId, handleUnauthorized, showViewsOnly],
  );

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [accessToken, load]);

  return (
    <section
      id="document-activity"
      className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl text-foreground">
            Document activity
          </h2>
          <p className="mt-1 text-sm text-muted">
            Authorised view counts measure successful preview requests after
            permission checks — not proof that someone read or understood the
            file. Downloads are tracked separately. Records cannot be edited
            through the application.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setShowViewsOnly(true)}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
              showViewsOnly
                ? "bg-accent text-white"
                : "border border-border hover:bg-accent-soft"
            }`}
          >
            Views
          </button>
          <button
            type="button"
            onClick={() => setShowViewsOnly(false)}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
              !showViewsOnly
                ? "bg-accent text-white"
                : "border border-border hover:bg-accent-soft"
            }`}
          >
            All events
          </button>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold hover:bg-accent-soft"
          >
            Refresh
          </button>
        </div>
      </div>

      {status === "loading" ? (
        <p className="mt-3 text-sm text-muted">Loading activity…</p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {status === "ready" && summary ? (
        <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-md border border-border/70 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Authorised views
            </dt>
            <dd className="mt-1 font-display text-2xl text-foreground">
              {summary.successful_views}
            </dd>
          </div>
          <div className="rounded-md border border-border/70 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Distinct viewers
            </dt>
            <dd className="mt-1 font-display text-2xl text-foreground">
              {summary.distinct_viewers ?? 0}
            </dd>
          </div>
          <div className="rounded-md border border-border/70 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Downloads
            </dt>
            <dd className="mt-1 font-display text-2xl text-foreground">
              {summary.successful_downloads}
            </dd>
          </div>
          <div className="rounded-md border border-border/70 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Latest view
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              {summary.latest_view_at
                ? formatDateTime(summary.latest_view_at)
                : "—"}
            </dd>
          </div>
        </dl>
      ) : null}

      {status === "ready" && events.length === 0 ? (
        <p className="mt-3 text-sm text-muted">
          {showViewsOnly
            ? "No authorised views recorded yet for this document."
            : "No events recorded yet."}
        </p>
      ) : null}
      {status === "ready" && events.length > 0 ? (
        <ul className="mt-4 max-h-96 space-y-2 overflow-auto text-sm">
          {events.map((event) => (
            <li
              key={event.id}
              className="rounded-md border border-border/70 px-3 py-2"
            >
              <p className="font-semibold">
                {event.action}{" "}
                <span
                  className={
                    event.outcome === "SUCCESS"
                      ? "text-accent-strong"
                      : "text-danger"
                  }
                >
                  {event.outcome}
                </span>
              </p>
              <p className="mt-0.5 text-xs text-muted">
                {formatDateTime(event.created_at)}
                {event.reason_code ? ` · ${event.reason_code}` : ""}
              </p>
              <p className="mt-1 text-xs text-foreground">
                {event.action === "DOCUMENT_VIEW"
                  ? `Viewer: ${viewerLabel(event)}`
                  : `Actor: ${viewerLabel(event)}`}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
