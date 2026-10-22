"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listMyPromotionRequests,
  submitPromotionRequest,
  type PromotionRequestItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function RequestOwnerPage() {
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
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
        <h1 className="font-display text-3xl tracking-tight">Request owner access</h1>
        <p className="text-sm text-muted">
          Only Viewer accounts can request promotion to Owner. Your current role
          is {user?.role ?? "unknown"}.
        </p>
      </div>
    );
  }

  const hasPending = items.some((item) => item.status === "PENDING");

  return (
    <div className="space-y-5">
      <header>
        <h1 className="font-display text-3xl tracking-tight text-foreground">
          Request owner access
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Approval grants Owner capabilities (upload and manage your own
          documents) without removing access you already have to documents shared
          with you.
        </p>
      </header>

      {message ? (
        <p role="status" className="text-sm text-accent-strong">
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {!hasPending ? (
        <form
          onSubmit={onSubmit}
          className="max-w-xl space-y-4 rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]"
        >
          <label className="block text-sm font-medium">
            Justification (optional)
            <textarea
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              rows={4}
              maxLength={2000}
              disabled={busy}
              className="mt-2 w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
          >
            {busy ? "Submitting…" : "Submit request"}
          </button>
        </form>
      ) : (
        <div className="rounded-xl border border-border bg-accent-soft/40 px-4 py-3 text-sm text-foreground">
          You already have a pending request. Wait for an administrator to
          approve or reject it — the submit button stays disabled until then.
        </div>
      )}

      <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
        <h2 className="font-display text-xl text-foreground">Your requests</h2>
        {status === "loading" ? (
          <p className="mt-3 text-sm text-muted">Loading…</p>
        ) : null}
        {status === "ready" && items.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No requests yet.</p>
        ) : null}
        {status === "ready" && items.length > 0 ? (
          <ul className="mt-3 space-y-3 text-sm">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded-md border border-border px-3 py-3"
              >
                <p className="font-semibold">{item.status}</p>
                <p className="text-muted">
                  Submitted {formatDateTime(item.created_at)}
                </p>
                {item.justification ? (
                  <p className="mt-1">{item.justification}</p>
                ) : null}
                {item.admin_note ? (
                  <p className="mt-1 text-muted">Admin note: {item.admin_note}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
