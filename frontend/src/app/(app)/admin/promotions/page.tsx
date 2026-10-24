"use client";

import { UserCog } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
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

      <PageHeader
        title="Owner promotion requests"
        description="Approve to grant Owner capabilities (Viewer to Owner only). Approval never assigns Admin. Existing document grants are preserved."
        actions={
          <Button type="button" variant="secondary" onClick={() => void load()}>
            Refresh
          </Button>
        }
      />

      {message ? <Alert tone="success">{message}</Alert> : null}
      {error && status !== "error" ? <Alert tone="error">{error}</Alert> : null}

      {status === "loading" ? (
        <div className="space-y-2" role="status" aria-busy>
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-28 w-full rounded-[var(--radius)]" />
          ))}
          <span className="sr-only">Loading pending requests...</span>
        </div>
      ) : null}

      {status === "error" ? (
        <Alert
          tone="error"
          action={
            <Button size="sm" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        >
          {error ?? "Unable to load requests."}
        </Alert>
      ) : null}

      {status === "ready" && items.length === 0 ? (
        <EmptyState
          title="No pending requests"
          description="When a Viewer asks for Owner access, their request appears here."
          icon={<UserCog className="h-5 w-5" strokeWidth={1.75} />}
        />
      ) : null}

      {status === "ready" && items.length > 0 ? (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id}>
              <Panel className="!p-4">
                <p className="font-semibold text-foreground">
                  {item.requester?.name ?? item.requester_id}
                </p>
                <p className="mt-1 text-sm text-muted">
                  {item.requester?.email} · submitted{" "}
                  {formatDateTime(item.created_at)}
                </p>
                {item.justification ? (
                  <p className="mt-3 rounded-[0.625rem] border border-border bg-accent-soft/40 px-3 py-2 text-sm">
                    {item.justification}
                  </p>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="primary"
                    disabled={busyId === item.id}
                    onClick={() => void review(item.id, "APPROVED")}
                  >
                    {busyId === item.id ? "Working..." : "Approve"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="danger"
                    disabled={busyId === item.id}
                    onClick={() => void review(item.id, "REJECTED")}
                  >
                    Reject
                  </Button>
                  {item.requester_id ? (
                    <Link
                      href={`/admin/users/${item.requester_id}`}
                      className="inline-flex min-h-8 items-center text-xs font-semibold text-accent-strong hover:underline"
                    >
                      View profile
                    </Link>
                  ) : null}
                </div>
              </Panel>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
