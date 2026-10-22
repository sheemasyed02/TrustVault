"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  ApiError,
  listAdminUsersRequest,
  patchAdminUserStatusRequest,
  type AdminUserListParams,
  type AdminUserSummary,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface FilterState {
  q: string;
  role: "" | "ADMIN" | "OWNER" | "VIEWER";
  is_active: "" | "true" | "false";
  promotion_status: "" | "PENDING" | "APPROVED" | "REJECTED" | "NONE";
}

const emptyFilters: FilterState = {
  q: "",
  role: "",
  is_active: "",
  promotion_status: "",
};

function toListParams(
  page: number,
  filters: FilterState,
): AdminUserListParams {
  return {
    page,
    page_size: 20,
    q: filters.q.trim() || undefined,
    role: filters.role || undefined,
    is_active:
      filters.is_active === ""
        ? undefined
        : filters.is_active === "true",
    promotion_status: filters.promotion_status || undefined,
  };
}

export default function AdminUsersPage() {
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [filters, setFilters] = useState<FilterState>(emptyFilters);
  const [applied, setApplied] = useState<FilterState>(emptyFilters);
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
    async (nextPage: number, nextFilters: FilterState, signal?: AbortSignal) => {
      if (!accessToken) return;
      setStatus("loading");
      setError(null);
      try {
        const data = await listAdminUsersRequest(
          accessToken,
          toListParams(nextPage, nextFilters),
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
    void load(1, applied, controller.signal);
    return () => controller.abort();
  }, [accessToken, applied, load]);

  function onApplyFilters(event: FormEvent) {
    event.preventDefault();
    setApplied({ ...filters });
  }

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
      await load(page, applied);
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
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
            Administration
          </p>
          <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
            User management
          </h1>
          <p className="mt-2 text-sm text-muted">
            Search and inspect registered accounts. Open a profile for activation,
            Viewer/Owner role changes, and owner-request review. Administrator
            accounts are labelled Admin and cannot be reassigned here. New public
            signups are always Viewers.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load(page, applied)}
          className="rounded-md border border-border px-3 py-2 text-sm font-semibold hover:bg-accent-soft"
        >
          Refresh
        </button>
      </header>

      <form
        onSubmit={onApplyFilters}
        className="grid gap-3 rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)] sm:grid-cols-2 lg:grid-cols-4"
      >
        <label className="text-sm sm:col-span-2">
          <span className="text-xs uppercase tracking-wide text-muted">
            Search name or email
          </span>
          <input
            value={filters.q}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, q: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
            placeholder="e.g. jane@company.com"
          />
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">Role</span>
          <select
            value={filters.role}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                role: e.target.value as FilterState["role"],
              }))
            }
            className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
          >
            <option value="">Any</option>
            <option value="ADMIN">Admin</option>
            <option value="OWNER">Owner</option>
            <option value="VIEWER">Viewer</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">
            Account status
          </span>
          <select
            value={filters.is_active}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                is_active: e.target.value as FilterState["is_active"],
              }))
            }
            className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
          >
            <option value="">Any</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </label>
        <label className="text-sm sm:col-span-2 lg:col-span-2">
          <span className="text-xs uppercase tracking-wide text-muted">
            Owner request
          </span>
          <select
            value={filters.promotion_status}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                promotion_status: e.target
                  .value as FilterState["promotion_status"],
              }))
            }
            className="mt-1 w-full rounded-md border border-border bg-white px-3 py-2"
          >
            <option value="">Any</option>
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved (latest)</option>
            <option value="REJECTED">Rejected (latest)</option>
            <option value="NONE">No pending request</option>
          </select>
        </label>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-2">
          <button
            type="submit"
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong"
          >
            Apply filters
          </button>
          <button
            type="button"
            onClick={() => {
              setFilters(emptyFilters);
              setApplied(emptyFilters);
            }}
            className="rounded-md border border-border px-4 py-2 text-sm font-semibold hover:bg-accent-soft"
          >
            Clear
          </button>
        </div>
      </form>

      {message ? (
        <p role="status" className="text-sm text-accent-strong">
          {message}
        </p>
      ) : null}
      {error && status !== "error" ? (
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
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm"
        >
          <p className="text-danger">{error ?? "Unable to load users."}</p>
          <button
            type="button"
            className="mt-2 font-semibold text-danger underline"
            onClick={() => void load(page, applied)}
          >
            Retry
          </button>
        </div>
      ) : null}

      {status === "ready" && users.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center">
          <p className="font-medium text-foreground">No users match</p>
          <p className="mt-2 text-sm text-muted">
            Try clearing filters or refreshing the list.
          </p>
        </div>
      ) : null}

      {status === "ready" && users.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3 font-semibold">User</th>
                <th className="px-4 py-3 font-semibold">Role</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Owner request</th>
                <th className="px-4 py-3 font-semibold">Registered</th>
                <th className="px-4 py-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((row) => {
                const isSelf = user?.id === row.id;
                return (
                  <tr key={row.id} className="border-b border-border/70 align-top">
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground">{row.name}</p>
                      <p className="text-xs text-muted">{row.email}</p>
                      <p className="mt-1 break-all font-mono text-[11px] text-muted">
                        {row.id}
                      </p>
                    </td>
                    <td className="px-4 py-3 font-semibold text-foreground">
                      {row.role === "ADMIN" ? (
                        <span className="text-accent-strong">Admin</span>
                      ) : row.role === "OWNER" ? (
                        "Owner"
                      ) : (
                        "Viewer"
                      )}
                    </td>
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
                      {row.promotion_request_status ?? "—"}
                      {row.promotion_requested_at ? (
                        <span className="mt-1 block text-xs">
                          {formatDateTime(row.promotion_requested_at)}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-muted">
                      {formatDateTime(row.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        <Link
                          href={`/admin/users/${row.id}`}
                          className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-strong"
                        >
                          View profile
                        </Link>
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
                      </div>
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
            onClick={() => void load(page - 1, applied)}
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
            onClick={() => void load(page + 1, applied)}
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
              ? `${pending.email} will be blocked on their next protected request.`
              : `${pending.email} will be able to use protected APIs again if credentials are valid.`
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
