"use client";

import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, SectionHeading } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  listMyPromotionRequests,
  submitPromotionRequest,
  type PromotionRequestItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function StatusBadge({ status }: { status: string }) {
  const upper = status.toUpperCase();
  if (upper === "PENDING") return <Badge tone="warning">Pending</Badge>;
  if (upper === "APPROVED") return <Badge tone="success">Approved</Badge>;
  if (upper === "REJECTED") return <Badge tone="danger">Rejected</Badge>;
  return <Badge tone="neutral">{status}</Badge>;
}

export default function RequestOwnerPage() {
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const justificationId = useId();
  const [items, setItems] = useState<PromotionRequestItem[]>([]);
  const [justification, setJustification] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listMyPromotionRequests(accessToken, signal);
        setItems(data);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setError(
          err instanceof ApiError ? err.detail : "Unable to load requests.",
        );
        setStatus("error");
      }
    },
    [accessToken, handleUnauthorized],
  );

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [accessToken, load]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await submitPromotionRequest(accessToken, justification.trim() || undefined);
      setMessage("Request submitted. An administrator will review it.");
      setJustification("");
      await load();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(
        err instanceof ApiError ? err.detail : "Unable to submit request.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (user?.role !== "VIEWER") {
    return (
      <div className="space-y-3">
        <PageHeader title="Request owner access" />
        <Alert tone="info">
          Only Viewer accounts can request promotion to Owner. Your current role
          is {user?.role ?? "unknown"}.
        </Alert>
      </div>
    );
  }

  const hasPending = items.some((item) => item.status === "PENDING");

  return (
    <div className="space-y-5">
      <PageHeader
        title="Request owner access"
        description="Approval grants Owner capabilities (upload and manage your own documents) without removing access you already have to documents shared with you."
      />

      {message ? <Alert tone="success">{message}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}

      {!hasPending ? (
        <Panel className="max-w-xl">
          <form onSubmit={onSubmit} className="space-y-4">
            <label htmlFor={justificationId} className="block text-sm">
              <span className="tv-label">Justification (optional)</span>
              <textarea
                id={justificationId}
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                rows={4}
                maxLength={2000}
                disabled={busy}
                className="tv-input min-h-[6rem] resize-y"
              />
            </label>
            <Button type="submit" variant="primary" disabled={busy}>
              {busy ? "Submitting..." : "Submit request"}
            </Button>
          </form>
        </Panel>
      ) : (
        <Alert tone="info">
          You already have a pending request. Wait for an administrator to
          approve or reject it — the submit form stays unavailable until then.
        </Alert>
      )}

      <Panel>
        <SectionHeading title="Your requests" />
        {status === "loading" ? (
          <div className="mt-3 space-y-2" role="status" aria-busy>
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <span className="sr-only">Loading...</span>
          </div>
        ) : null}
        {status === "ready" && items.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No requests yet.</p>
        ) : null}
        {status === "ready" && items.length > 0 ? (
          <ul className="mt-3 space-y-3 text-sm">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded-[0.75rem] border border-border px-3 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <StatusBadge status={item.status} />
                  <p className="text-xs text-muted">
                    Submitted {formatDateTime(item.created_at)}
                  </p>
                </div>
                {item.justification ? (
                  <p className="mt-2 text-foreground">{item.justification}</p>
                ) : null}
                {item.admin_note ? (
                  <p className="mt-1 text-muted">
                    Admin note: {item.admin_note}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </Panel>
    </div>
  );
}
