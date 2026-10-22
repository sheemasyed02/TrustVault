"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listAdminPromotionsRequest,
  reviewPromotionRequest,
  type PromotionRequestItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function AdminPromotionsPage() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [items, setItems] = useState<PromotionRequestItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listAdminPromotionsRequest(
          accessToken,
          { status: "PENDING", page_size: 50 },
          signal,
        );
        setItems(data.results);
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

  async function review(id: string, decision: "APPROVED" | "REJECTED") {
    if (!accessToken || busyId) return;
    setBusyId(id);
    setMessage(null);
    setError(null);
    try {
      await reviewPromotionRequest(accessToken, id, { decision });
      setMessage(
        decision === "APPROVED"
          ? "Request approved — user is now an Owner."
          : "Request rejected.",
      );
      await load();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(err instanceof ApiError ? err.detail : "Review failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-5">
      <Link
        href="/admin"
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← Admin dashboard
      </Link>

      <header>
        <h1 className="font-display text-3xl tracking-tight text-foreground">
          Owner promotion requests
        </h1>
        <p className="mt-2 text-sm text-muted">
          Approve to grant Owner capabilities without removing the requester’s
          existing document grants.
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

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading pending requests…
        </p>
      ) : null}

      {status === "error" ? (
        <button
          type="button"
          className="text-sm font-semibold text-danger underline"
          onClick={() => void load()}
        >
          Retry
        </button>
      ) : null}

      {status === "ready" && items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center">
          <p className="font-medium text-foreground">No pending requests</p>
          <p className="mt-2 text-sm text-muted">
            When a Viewer asks for Owner access, their request appears here.
          </p>
        </div>
      ) : null}

      {status === "ready" && items.length > 0 ? (
        <ul className="space-y-3">
          {items.map((item) => (
            <li
              key={item.id}
              className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]"
            >
              <p className="font-semibold text-foreground">
                {item.requester?.name ?? item.requester_id}
              </p>
              <p className="text-sm text-muted">
                {item.requester?.email} · submitted{" "}
                {formatDateTime(item.created_at)}
              </p>
              {item.justification ? (
                <p className="mt-2 text-sm">{item.justification}</p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busyId === item.id}
                  onClick={() => void review(item.id, "APPROVED")}
                  className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
                >
                  Approve
                </button>
                <button
                  type="button"
                  disabled={busyId === item.id}
                  onClick={() => void review(item.id, "REJECTED")}
                  className="rounded-md border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger disabled:opacity-60"
                >
                  Reject
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
