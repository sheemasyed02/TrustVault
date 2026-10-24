"use client";

import { RefreshCw, Search, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClassName } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
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

function RoleBadge({ role }: { role: AdminUserSummary["role"] }) {
  if (role === "ADMIN") return <Badge tone="accent">Admin</Badge>;
  if (role === "OWNER") return <Badge tone="warning">Owner</Badge>;
  return <Badge tone="neutral">Viewer</Badge>;
}

function StatusBadge({ active }: { active: boolean }) {
  return active ? (
    <Badge tone="success">Active</Badge>
  ) : (
    <Badge tone="danger">Inactive</Badge>
  );
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

      <PageHeader
        title="User management"
        description="Search registered accounts. Open a profile for role and owner-request review. Administrator accounts cannot be reassigned here."
        actions={
          <Button
            type="button"
            variant="secondary"
            onClick={() => void load(page, applied)}
          >
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            Refresh
          </Button>
        }
      />

      <form
        onSubmit={onApplyFilters}
        className="grid gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-sm)] sm:grid-cols-2 lg:grid-cols-4 sm:p-5"
      >
        <label className="text-sm sm:col-span-2">
          <span className="tv-label">Search name or email</span>
          <span className="relative block">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
              strokeWidth={1.75}
              aria-hidden
            />
            <input
              value={filters.q}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, q: e.target.value }))
              }
              className="tv-input pl-9"
              placeholder="e.g. jane@company.com"
            />
          </span>
        </label>
        <label className="text-sm">
          <span className="tv-label">Role</span>
          <select
            value={filters.role}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                role: e.target.value as FilterState["role"],
              }))
            }
            className="tv-input"
          >
            <option value="">Any</option>
            <option value="ADMIN">Admin</option>
            <option value="OWNER">Owner</option>
            <option value="VIEWER">Viewer</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="tv-label">Account status</span>
          <select
            value={filters.is_active}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                is_active: e.target.value as FilterState["is_active"],
              }))
            }
            className="tv-input"
          >
            <option value="">Any</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </label>
        <label className="text-sm sm:col-span-2 lg:col-span-2">
          <span className="tv-label">Owner request</span>
          <select
            value={filters.promotion_status}
            onChange={(e) =>
              setFilters((prev) => ({
                ...prev,
                promotion_status: e.target
                  .value as FilterState["promotion_status"],
              }))
            }
            className="tv-input"
          >
            <option value="">Any</option>
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved (latest)</option>
            <option value="REJECTED">Rejected (latest)</option>
            <option value="NONE">No pending request</option>
          </select>
        </label>
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-2">
          <Button type="submit" variant="primary">
            Apply filters
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setFilters(emptyFilters);
              setApplied(emptyFilters);
            }}
          >
            Clear
          </Button>
        </div>
      </form>

      {message ? <Alert tone="success">{message}</Alert> : null}
      {error && status !== "error" ? <Alert tone="error">{error}</Alert> : null}

      {status === "loading" ? (
        <div className="space-y-2" role="status" aria-busy>
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full rounded-[0.75rem]" />
          ))}
          <span className="sr-only">Loading users...</span>
        </div>
      ) : null}

      {status === "error" ? (
        <Alert
          tone="error"
          action={
            <Button size="sm" variant="secondary" onClick={() => void load(page, applied)}>
              Retry
            </Button>
          }
        >
          {error ?? "Unable to load users."}
        </Alert>
      ) : null}

      {status === "ready" && users.length === 0 ? (
        <EmptyState
          title="No users match"
          description="Try clearing filters or refreshing the list."
          icon={<Users className="h-5 w-5" strokeWidth={1.75} />}
        />
      ) : null}

      {status === "ready" && users.length > 0 ? (
        <div className="tv-table-wrap">
          <table className="tv-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Status</th>
                <th className="hidden md:table-cell">Owner request</th>
                <th className="hidden lg:table-cell">Registered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((row) => {
                const isSelf = user?.id === row.id;
                return (
                  <tr key={row.id}>
                    <td>
                      <p className="font-medium text-foreground">{row.name}</p>
                      <p className="text-xs text-muted">{row.email}</p>
                      <p
                        className="mt-1 max-w-[12rem] truncate font-mono text-[11px] text-muted"
                        title={row.id}
                      >
                        {row.id}
                      </p>
                    </td>
                    <td>
                      <RoleBadge role={row.role} />
                    </td>
                    <td>
                      <StatusBadge active={row.is_active} />
                    </td>
                    <td className="hidden text-muted md:table-cell">
                      {row.promotion_request_status ?? "—"}
                      {row.promotion_requested_at ? (
                        <span className="mt-1 block text-xs">
                          {formatDateTime(row.promotion_requested_at)}
                        </span>
                      ) : null}
                    </td>
                    <td className="hidden text-muted lg:table-cell">
                      {formatDateTime(row.created_at)}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-2">
                        <Link
                          href={`/admin/users/${row.id}`}
                          className={buttonClassName({
                            variant: "primary",
                            size: "sm",
                          })}
                        >
                          View profile
                        </Link>
                        <Button
                          type="button"
                          size="sm"
                          variant={row.is_active ? "danger" : "secondary"}
                          disabled={isSelf && row.is_active}
                          title={
                            isSelf && row.is_active
                              ? "You cannot deactivate your own account"
                              : undefined
                          }
                          onClick={() => setPending(row)}
                        >
                          {row.is_active ? "Deactivate" : "Activate"}
                        </Button>
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
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius)] border border-border bg-surface px-4 py-3 text-sm shadow-[var(--shadow-sm)]">
          <p className="text-muted">
            Page {page} of {totalPages} ({total} users)
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={page <= 1}
              onClick={() => void load(page - 1, applied)}
            >
              Previous
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => void load(page + 1, applied)}
            >
              Next
            </Button>
          </div>
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
