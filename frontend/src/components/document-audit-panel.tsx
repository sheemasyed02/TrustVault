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

type FocusFilter =
  | "external_views"
  | "owner_views"
  | "downloads"
  | "denied"
  | "all";

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

const FOCUS_OPTIONS: { id: FocusFilter; label: string }[] = [
  { id: "external_views", label: "External views" },
  { id: "owner_views", label: "My views" },
  { id: "downloads", label: "Downloads" },
  { id: "denied", label: "Denied" },
  { id: "all", label: "All events" },
];

/** Owner-only document activity — external views are the primary dashboard metric. */
export function DocumentAuditPanel({ documentId }: DocumentAuditPanelProps) {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [events, setEvents] = useState<AuditEventItem[]>([]);
  const [summary, setSummary] = useState<DocumentAuditSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<FocusFilter>("external_views");

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listDocumentAuditRequest(
          accessToken,
          documentId,
          { page_size: 50, focus },
          signal,
        );
        setEvents(data.results);
        setSummary(data.summary ?? null);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setError(
          err instanceof ApiError
            ? err.detail
            : "Unable to load document activity.",
        );
        setStatus("error");
      }
    },
    [accessToken, documentId, focus, handleUnauthorized],
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
            External views are successful previews by others. Your own opens stay
            in the trail but are excluded from those totals.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold hover:bg-accent-soft"
        >
          Refresh
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {FOCUS_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => setFocus(option.id)}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
              focus === option.id
                ? "bg-accent text-white"
                : "border border-border hover:bg-accent-soft"
            }`}
          >
            {option.label}
          </button>
        ))}
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
              External views
            </dt>
            <dd className="mt-1 font-display text-2xl text-foreground">
              {summary.external_views ?? 0}
            </dd>
          </div>
          <div className="rounded-md border border-border/70 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Distinct external viewers
            </dt>
            <dd className="mt-1 font-display text-2xl text-foreground">
              {summary.distinct_external_viewers ?? 0}
            </dd>
          </div>
          <div className="rounded-md border border-border/70 px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-muted">
              My views (trail)
            </dt>
            <dd className="mt-1 font-display text-2xl text-foreground">
              {summary.owner_self_views ?? 0}
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
        </dl>
      ) : null}

      {status === "ready" && events.length === 0 ? (
        <p className="mt-3 text-sm text-muted">
          No events in this filter yet.
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
                {event.action.replaceAll("_", " ")}{" "}
                <span
                  className={
                    event.outcome === "SUCCESS"
                      ? "text-accent-strong"
                      : "text-danger"
                  }
                >
                  {event.outcome}
                </span>
                {event.is_owner_self_view ? (
                  <span className="ml-2 text-xs font-normal text-muted">
                    (your view)
                  </span>
                ) : null}
              </p>
              <p className="mt-0.5 text-xs text-muted" title={event.created_at}>
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
