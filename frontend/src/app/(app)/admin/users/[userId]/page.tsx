"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  ApiError,
  getAdminUserProfileRequest,
  patchAdminUserRoleRequest,
  patchAdminUserStatusRequest,
  reviewPromotionRequest,
  type AdminUserProfile,
  type UserRole,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function AdminUserProfilePage() {
  const params = useParams<{ userId: string }>();
  const { user, accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [profile, setProfile] = useState<AdminUserProfile | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [roleBusy, setRoleBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [confirmStatus, setConfirmStatus] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!accessToken || !params.userId) return;
      setStatus("loading");
      setError(null);
      setErrorCode(null);
      try {
        const data = await getAdminUserProfileRequest(
          accessToken,
          params.userId,
          signal,
        );
        setProfile(data);
        setStatus("ready");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (handleUnauthorized(err)) return;
        setProfile(null);
        if (err instanceof ApiError) {
          setError(err.detail);
          setErrorCode(err.status);
        } else {
          setError("Unable to load user profile.");
          setErrorCode(null);
        }
        setStatus("error");
      }
    },
    [accessToken, handleUnauthorized, params.userId],
  );

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [accessToken, load]);

  async function onRoleChange(role: UserRole) {
    if (!accessToken || !profile || roleBusy || profile.role === role) return;
    setRoleBusy(true);
    setMessage(null);
    setError(null);
    try {
      await patchAdminUserRoleRequest(accessToken, profile.id, role);
      setMessage(`Role updated to ${role}.`);
      await load();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(err instanceof ApiError ? err.detail : "Unable to update role.");
    } finally {
      setRoleBusy(false);
    }
  }

  async function confirmToggleActive() {
    if (!accessToken || !profile || busy) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const nextActive = !profile.is_active;
    try {
      await patchAdminUserStatusRequest(accessToken, profile.id, nextActive);
      setMessage(
        nextActive
          ? `Activated ${profile.email}.`
          : `Deactivated ${profile.email}.`,
      );
      setConfirmStatus(false);
      await load();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(
        err instanceof ApiError
          ? err.detail
          : "Unable to update account status.",
      );
      setConfirmStatus(false);
    } finally {
      setBusy(false);
    }
  }

  async function onReview(decision: "APPROVED" | "REJECTED") {
    if (!accessToken || !profile?.latest_promotion || reviewBusy) return;
    if (profile.latest_promotion.status !== "PENDING") return;
    setReviewBusy(true);
    setMessage(null);
    setError(null);
    try {
      await reviewPromotionRequest(accessToken, profile.latest_promotion.id, {
        decision,
      });
      setMessage(
        decision === "APPROVED"
          ? "Owner request approved — role is now OWNER."
          : "Owner request rejected.",
      );
      await load();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(err instanceof ApiError ? err.detail : "Review failed.");
    } finally {
      setReviewBusy(false);
    }
  }

  const isSelf = user?.id === profile?.id;
  const pendingPromotion =
    profile?.latest_promotion?.status === "PENDING"
      ? profile.latest_promotion
      : null;

  return (
    <div className="space-y-5">
      <Link
        href="/admin/users"
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← User management
      </Link>

      {status === "loading" ? (
        <p className="text-sm text-muted" role="status">
          Loading profile…
        </p>
      ) : null}

      {status === "error" ? (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-4 text-sm"
        >
          <p className="text-danger">{error}</p>
          <p className="mt-2 text-muted">
            {errorCode === 404
              ? "No registered user matches this ID."
              : "Profile details from the failed response are not shown."}
          </p>
          <button
            type="button"
            className="mt-3 font-semibold text-danger underline"
            onClick={() => void load()}
          >
            Retry
          </button>
        </div>
      ) : null}

      {message ? (
        <p role="status" className="text-sm text-accent-strong">
          {message}
        </p>
      ) : null}
      {error && status === "ready" ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {status === "ready" && profile ? (
        <>
          <header className="rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow)]">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
              User profile
            </p>
            <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
              {profile.name}
            </h1>
            <p className="mt-1 text-sm text-muted">{profile.email}</p>
            <dl className="mt-6 grid gap-4 sm:grid-cols-2">
              <Detail label="User ID" value={profile.id} mono />
              <Detail label="Role" value={profile.role} />
              <Detail
                label="Account status"
                value={profile.is_active ? "Active" : "Inactive"}
              />
              <Detail
                label="Registered"
                value={formatDateTime(profile.created_at)}
              />
              <Detail
                label="Last updated"
                value={formatDateTime(profile.updated_at)}
              />
              <Detail
                label="Owner request"
                value={
                  profile.promotion_request_status
                    ? `${profile.promotion_request_status}${
                        profile.promotion_requested_at
                          ? ` · ${formatDateTime(profile.promotion_requested_at)}`
                          : ""
                      }`
                    : "None"
                }
              />
            </dl>
          </header>

          <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
            <h2 className="font-display text-xl text-foreground">
              Account activity
            </h2>
            <p className="mt-1 text-sm text-muted">
              Counts from the live database. This profile never includes document
              contents or storage locations.
            </p>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Owned documents"
                value={profile.activity.owned_documents}
              />
              <Stat
                label="Active grants received"
                value={profile.activity.active_grants_received}
              />
              <Stat
                label="Audit events (as actor)"
                value={profile.activity.audit_events_as_actor}
              />
              <Stat
                label="Denied attempts"
                value={profile.activity.denied_audit_events_as_actor}
              />
            </dl>
          </section>

          {pendingPromotion ? (
            <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
              <h2 className="font-display text-xl text-foreground">
                Pending owner request
              </h2>
              <p className="mt-2 text-sm text-muted">
                Submitted {formatDateTime(pendingPromotion.created_at)}
              </p>
              {pendingPromotion.justification ? (
                <p className="mt-3 rounded-md border border-border bg-white px-3 py-2 text-sm">
                  {pendingPromotion.justification}
                </p>
              ) : (
                <p className="mt-3 text-sm text-muted">No justification provided.</p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={reviewBusy}
                  onClick={() => void onReview("APPROVED")}
                  className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
                >
                  {reviewBusy ? "Working…" : "Approve → Owner"}
                </button>
                <button
                  type="button"
                  disabled={reviewBusy}
                  onClick={() => void onReview("REJECTED")}
                  className="rounded-md border border-danger/40 px-4 py-2 text-sm font-semibold text-danger disabled:opacity-60"
                >
                  Reject
                </button>
              </div>
            </section>
          ) : null}

          {profile.latest_promotion &&
          profile.latest_promotion.status !== "PENDING" ? (
            <section className="rounded-xl border border-border bg-surface p-5 text-sm shadow-[var(--shadow)]">
              <h2 className="font-display text-xl text-foreground">
                Latest owner request
              </h2>
              <p className="mt-2 text-muted">
                {profile.latest_promotion.status} · submitted{" "}
                {formatDateTime(profile.latest_promotion.created_at)}
                {profile.latest_promotion.reviewed_at
                  ? ` · reviewed ${formatDateTime(profile.latest_promotion.reviewed_at)}`
                  : ""}
              </p>
              {profile.latest_promotion.admin_note ? (
                <p className="mt-2">Admin note: {profile.latest_promotion.admin_note}</p>
              ) : null}
            </section>
          ) : null}

          <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
            <h2 className="font-display text-xl text-foreground">
              Manage account
            </h2>
            <div className="mt-4 flex flex-wrap items-end gap-4">
              <label className="text-sm">
                <span className="mb-1 block font-medium">Platform role</span>
                <select
                  value={profile.role}
                  disabled={roleBusy}
                  onChange={(e) =>
                    void onRoleChange(e.target.value as UserRole)
                  }
                  className="rounded-md border border-border bg-white px-3 py-2 text-sm"
                >
                  <option value="VIEWER">VIEWER</option>
                  <option value="OWNER">OWNER</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
              </label>
              <button
                type="button"
                disabled={Boolean(isSelf && profile.is_active)}
                title={
                  isSelf && profile.is_active
                    ? "You cannot deactivate your own account"
                    : undefined
                }
                onClick={() => setConfirmStatus(true)}
                className="rounded-md border border-border px-4 py-2 text-sm font-semibold hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
              >
                {profile.is_active ? "Deactivate account" : "Activate account"}
              </button>
            </div>
            <p className="mt-3 text-xs text-muted">
              Role changes are enforced by the server. The last active
              administrator cannot be deactivated. Passwords and tokens are never
              shown here.
            </p>
          </section>
        </>
      ) : null}

      <ConfirmDialog
        open={confirmStatus}
        title={
          profile?.is_active
            ? "Deactivate this account?"
            : "Activate this account?"
        }
        description={
          profile
            ? profile.is_active
              ? `${profile.email} will be blocked on their next protected request.`
              : `${profile.email} will regain access if credentials are valid.`
            : ""
        }
        confirmLabel={profile?.is_active ? "Deactivate" : "Activate"}
        danger={profile?.is_active === true}
        busy={busy}
        onCancel={() => {
          if (!busy) setConfirmStatus(false);
        }}
        onConfirm={() => void confirmToggleActive()}
      />
    </div>
  );
}

function Detail({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd
        className={`mt-1 break-all text-sm text-foreground ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border/70 px-3 py-2">
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 font-display text-2xl text-foreground">{value}</dd>
    </div>
  );
}
