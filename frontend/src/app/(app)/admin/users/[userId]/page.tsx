"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, SectionHeading } from "@/components/ui/page-header";
import { Panel, StatCard } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  getAdminUserProfileRequest,
  patchAdminUserRoleRequest,
  patchAdminUserStatusRequest,
  reviewPromotionRequest,
  type AdminUserProfile,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function RoleBadge({ role }: { role: string }) {
  const upper = role.toUpperCase();
  if (upper === "ADMIN") return <Badge tone="accent">Admin</Badge>;
  if (upper === "OWNER") return <Badge tone="warning">Owner</Badge>;
  return <Badge tone="neutral">{upper === "VIEWER" ? "Viewer" : role}</Badge>;
}

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

  const isSelf = user?.id === profile?.id;

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

  async function onRoleChange(role: "OWNER" | "VIEWER") {
    if (
      !accessToken ||
      !profile ||
      roleBusy ||
      profile.role === "ADMIN" ||
      profile.role === role ||
      isSelf
    ) {
      return;
    }
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
        <div className="space-y-3" role="status" aria-busy>
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-40 w-full rounded-[var(--radius)]" />
          <span className="sr-only">Loading profile...</span>
        </div>
      ) : null}

      {status === "error" ? (
        <Alert
          tone="error"
          title={error ?? "Unable to load user profile."}
          action={
            <Button size="sm" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          }
        >
          {errorCode === 404
            ? "No registered user matches this ID."
            : "Profile details from the failed response are not shown."}
        </Alert>
      ) : null}

      {message ? <Alert tone="success">{message}</Alert> : null}
      {error && status === "ready" ? <Alert tone="error">{error}</Alert> : null}

      {status === "ready" && profile ? (
        <>
          <Panel>
            <PageHeader
              eyebrow="User profile"
              title={profile.name}
              description={profile.email}
              actions={
                <div className="flex flex-wrap gap-2">
                  <RoleBadge role={profile.role} />
                  {profile.is_active ? (
                    <Badge tone="success">Active</Badge>
                  ) : (
                    <Badge tone="danger">Inactive</Badge>
                  )}
                </div>
              }
            />
            <dl className="mt-6 grid gap-4 sm:grid-cols-2">
              <Detail label="User ID" value={profile.id} mono />
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
          </Panel>

          <Panel>
            <SectionHeading
              title="Account activity"
              description="Counts from the live database. This profile never includes document contents or storage locations."
            />
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Owned documents"
                value={profile.activity.owned_documents}
              />
              <StatCard
                label="Active grants received"
                value={profile.activity.active_grants_received}
              />
              <StatCard
                label="Audit events (as actor)"
                value={profile.activity.audit_events_as_actor}
              />
              <StatCard
                label="Denied attempts"
                value={profile.activity.denied_audit_events_as_actor}
              />
            </dl>
          </Panel>

          {pendingPromotion ? (
            <Panel>
              <SectionHeading title="Pending owner request" />
              <p className="mt-2 text-sm text-muted">
                Submitted {formatDateTime(pendingPromotion.created_at)}
              </p>
              {pendingPromotion.justification ? (
                <p className="mt-3 rounded-[0.625rem] border border-border bg-accent-soft/40 px-3 py-2 text-sm">
                  {pendingPromotion.justification}
                </p>
              ) : (
                <p className="mt-3 text-sm text-muted">No justification provided.</p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="primary"
                  disabled={reviewBusy}
                  onClick={() => void onReview("APPROVED")}
                >
                  {reviewBusy ? "Working..." : "Approve -> Owner"}
                </Button>
                <Button
                  type="button"
                  variant="danger"
                  disabled={reviewBusy}
                  onClick={() => void onReview("REJECTED")}
                >
                  Reject
                </Button>
              </div>
            </Panel>
          ) : null}

          {profile.latest_promotion &&
          profile.latest_promotion.status !== "PENDING" ? (
            <Panel>
              <SectionHeading title="Latest owner request" />
              <p className="mt-2 text-sm text-muted">
                {profile.latest_promotion.status} · submitted{" "}
                {formatDateTime(profile.latest_promotion.created_at)}
                {profile.latest_promotion.reviewed_at
                  ? ` · reviewed ${formatDateTime(profile.latest_promotion.reviewed_at)}`
                  : ""}
              </p>
              {profile.latest_promotion.admin_note ? (
                <p className="mt-2 text-sm">
                  Admin note: {profile.latest_promotion.admin_note}
                </p>
              ) : null}
            </Panel>
          ) : null}

          <Panel>
            <SectionHeading title="Manage account" />
            <div className="mt-4 flex flex-wrap items-end gap-4">
              {profile.role === "ADMIN" ? (
                <div className="text-sm">
                  <span className="tv-label">Platform role</span>
                  <p className="rounded-[0.625rem] border border-border bg-accent-soft/40 px-3 py-2 font-semibold text-accent-strong">
                    ADMIN
                  </p>
                  <p className="mt-1 max-w-sm text-xs text-muted">
                    Administrator accounts are provisioned securely and cannot
                    be reassigned through Manage Users.
                  </p>
                </div>
              ) : (
                <label className="text-sm">
                  <span className="tv-label">Platform role</span>
                  <select
                    value={profile.role === "OWNER" ? "OWNER" : "VIEWER"}
                    disabled={roleBusy || isSelf}
                    onChange={(e) =>
                      void onRoleChange(e.target.value as "OWNER" | "VIEWER")
                    }
                    className="tv-input"
                  >
                    <option value="VIEWER">Viewer</option>
                    <option value="OWNER">Owner</option>
                  </select>
                  {isSelf ? (
                    <p className="mt-1 text-xs text-muted">
                      You cannot change your own role.
                    </p>
                  ) : null}
                </label>
              )}
              <Button
                type="button"
                variant={profile.is_active ? "danger" : "secondary"}
                disabled={Boolean(isSelf && profile.is_active)}
                title={
                  isSelf && profile.is_active
                    ? "You cannot deactivate your own account"
                    : undefined
                }
                onClick={() => setConfirmStatus(true)}
              >
                {profile.is_active ? "Deactivate account" : "Activate account"}
              </Button>
            </div>
            <p className="mt-3 text-xs text-muted">
              Ordinary role changes are Viewer ↔ Owner only and are enforced by
              the server. Admin cannot be assigned here. The last active
              administrator cannot be deactivated. Passwords and tokens are never
              shown here.
            </p>
          </Panel>
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
    <div className="rounded-[0.75rem] border border-border bg-accent-soft/40 px-4 py-3">
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
