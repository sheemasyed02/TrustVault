"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  ApiError,
  listAdminUsersRequest,
  patchAdminUserStatusRequest,
  type AdminUserSummary,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function AdminUsersPage() {
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<AdminUserSummary | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (nextPage: number, signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listAdminUsersRequest(
          accessToken,
          { page: nextPage, page_size: 20 },
          signal,
        );
        setUsers(data.results);
        setPage(data.page);
        setTotalPages(data.total_pages);
        setTotal(data.total);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setUsers([]);
        setError(
          err instanceof ApiError ? err.detail : "Unable to load users.",
        );
        setStatus("error");
      }
    },
    [accessToken, handleUnauthorized],
  );

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void load(1, controller.signal);
    return () => controller.abort();
  }, [accessToken, load]);

  async function confirmStatusChange() {
    if (!accessToken || !pending || busy) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const nextActive = !pending.is_active;
    try {
      await patchAdminUserStatusRequest(accessToken, pending.id, nextActive);
      setMessage(
        nextActive
          ? `Activated ${pending.email}.`
          : `Deactivated ${pending.email}.`,
      );
      setPending(null);
      await load(page);
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(
        err instanceof ApiError
          ? err.detail
          : "Unable to update account status.",
      );
      setPending(null);
    } finally {
      setBusy(false);
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

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl tracking-tight text-foreground">
            User management
          </h1>
          <p className="mt-2 text-sm text-muted">
            Activate or deactivate accounts. Role changes are not available.
            Disabled users are blocked on their next protected API request.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load(page)}
          className="rounded-md border border-border px-3 py-2 text-sm font-semibold hover:bg-accent-soft"
        >
          Refresh
        </button>
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
          Loading users…
        </p>
      ) : null}

      {status === "error" ? (
        <button
          type="button"
          className="text-sm font-semibold text-danger underline"
          onClick={() => void load(page)}
        >
          Retry
        </button>
      ) : null}

      {status === "ready" && users.length === 0 ? (
        <p className="text-sm text-muted" role="status">
          No users found.
        </p>
      ) : null}

      {status === "ready" && users.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3 font-semibold">User</th>
                <th className="px-4 py-3 font-semibold">Role</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Created</th>
                <th className="px-4 py-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((row) => {
                const isSelf = user?.id === row.id;
                return (
                  <tr key={row.id} className="border-b border-border/70">
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground">{row.name}</p>
                      <p className="text-xs text-muted">{row.email}</p>
                      <p className="mt-1 break-all font-mono text-[11px] text-muted">
                        {row.id}
                      </p>
                    </td>
                    <td className="px-4 py-3">{row.role}</td>
                    <td className="px-4 py-3">
                      {row.is_active ? (
                        <span className="font-semibold text-accent-strong">
                          Active
                        </span>
                      ) : (
                        <span className="font-semibold text-danger">
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted">
                      {formatDateTime(row.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        disabled={isSelf && row.is_active}
                        title={
                          isSelf && row.is_active
                            ? "You cannot deactivate your own account"
                            : undefined
                        }
                        onClick={() => setPending(row)}
                        className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {row.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {status === "ready" && totalPages > 1 ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => void load(page - 1)}
            className="rounded-md border border-border px-3 py-1.5 font-semibold disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-muted">
            Page {page} of {totalPages} ({total} users)
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => void load(page + 1)}
            className="rounded-md border border-border px-3 py-1.5 font-semibold disabled:opacity-50"
          >
            Next
          </button>
        </div>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        title={
          pending?.is_active ? "Deactivate this account?" : "Activate this account?"
        }
        description={
          pending
            ? pending.is_active
              ? `${pending.email} will be blocked on their next protected request. Existing JWTs are not a permission cache for active status.`
              : `${pending.email} will be able to sign in and use protected APIs again if their credentials are valid.`
            : ""
        }
        confirmLabel={pending?.is_active ? "Deactivate" : "Activate"}
        danger={pending?.is_active === true}
        busy={busy}
        onCancel={() => {
          if (!busy) setPending(null);
        }}
        onConfirm={() => void confirmStatusChange()}
      />
    </div>
  );
}
