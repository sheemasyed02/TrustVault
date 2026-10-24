"use client";

import { Eye, EyeOff, KeyRound, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, SectionHeading } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import {
  ApiError,
  changePasswordRequest,
  updateCurrentUserProfileRequest,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  disabled,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  disabled: boolean;
  hint?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="tv-label mb-0">
          {label}
        </label>
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs font-semibold text-accent-strong hover:underline"
          onClick={() => setVisible((v) => !v)}
          aria-pressed={visible}
        >
          {visible ? (
            <EyeOff className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          ) : (
            <Eye className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          )}
          {visible ? "Hide" : "Show"}
        </button>
      </div>
      <input
        id={id}
        name={id}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        required
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="tv-input"
      />
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  const upper = role.toUpperCase();
  if (upper === "ADMIN") return <Badge tone="accent">Admin</Badge>;
  if (upper === "OWNER") return <Badge tone="warning">Owner</Badge>;
  return <Badge tone="neutral">{upper === "VIEWER" ? "Viewer" : role}</Badge>;
}

export default function ProfilePage() {
  const { user, accessToken, refreshUser, logout } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const router = useRouter();

  const nameId = useId();
  const currentPasswordId = useId();
  const newPasswordId = useId();
  const confirmPasswordId = useId();

  const [name, setName] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  useEffect(() => {
    if (user) setName(user.name);
  }, [user]);

  if (!user) return null;

  async function onSaveProfile(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || !user || profileBusy) return;
    const trimmed = name.trim();
    if (trimmed.length < 2) {
      setProfileError("Name must be at least 2 characters.");
      return;
    }
    setProfileBusy(true);
    setProfileError(null);
    setProfileMessage(null);
    try {
      const updated = await updateCurrentUserProfileRequest(accessToken, {
        name: trimmed,
      });
      setName(updated.name);
      await refreshUser();
      setProfileMessage("Profile updated.");
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setProfileError(
        err instanceof ApiError ? err.detail : "Unable to update profile.",
      );
    } finally {
      setProfileBusy(false);
    }
  }

  async function onChangePassword(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || passwordBusy) return;
    if (newPassword !== confirmPassword) {
      setPasswordError("New password and confirmation do not match.");
      return;
    }
    if (newPassword.length < 10) {
      setPasswordError("New password must be at least 10 characters.");
      return;
    }
    setPasswordBusy(true);
    setPasswordError(null);
    try {
      await changePasswordRequest(accessToken, {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      // Clear in-memory session; JWT revocation store is not implemented.
      logout();
      router.replace("/?passwordChanged=1");
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setPasswordError(
        err instanceof ApiError ? err.detail : "Unable to change password.",
      );
    } finally {
      setPasswordBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Profile"
        description="Your personal details from the authenticated session. Role and account status are managed by administrators."
      />

      <Panel>
        <SectionHeading
          title="Account"
          description="Details returned by the current-user API."
          actions={
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
              <UserRound className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            </span>
          }
        />

        <dl className="mt-5 grid gap-4 sm:grid-cols-2">
          <div className="rounded-[0.75rem] border border-border bg-accent-soft/40 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">Email</dt>
            <dd className="mt-1 break-all text-sm font-medium text-foreground">
              {user.email}
            </dd>
            <p className="mt-1 text-xs text-muted">
              Login identity cannot be changed here.
            </p>
          </div>
          <div className="rounded-[0.75rem] border border-border bg-accent-soft/40 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">Role</dt>
            <dd className="mt-2">
              <RoleBadge role={user.role} />
            </dd>
          </div>
          <div className="rounded-[0.75rem] border border-border bg-accent-soft/40 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Account status
            </dt>
            <dd className="mt-2">
              {user.is_active ? (
                <Badge tone="success">Active</Badge>
              ) : (
                <Badge tone="danger">Inactive</Badge>
              )}
            </dd>
          </div>
          <div className="rounded-[0.75rem] border border-border bg-accent-soft/40 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-muted">
              Registered
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              {formatDateTime(user.created_at)}
            </dd>
          </div>
        </dl>

        <form
          onSubmit={(e) => void onSaveProfile(e)}
          className="mt-6 space-y-4 border-t border-border pt-5"
          noValidate
        >
          <label htmlFor={nameId} className="block max-w-md text-sm">
            <span className="tv-label">Full name</span>
            <input
              id={nameId}
              name="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              minLength={2}
              maxLength={255}
              disabled={profileBusy}
              className="tv-input"
            />
          </label>
          {profileError ? <Alert tone="error">{profileError}</Alert> : null}
          {profileMessage ? (
            <Alert tone="success">{profileMessage}</Alert>
          ) : null}
          <Button
            type="submit"
            variant="primary"
            disabled={profileBusy || name.trim() === user.name}
          >
            {profileBusy ? "Saving..." : "Save name"}
          </Button>
        </form>
      </Panel>

      <Panel>
        <SectionHeading
          title="Change password"
          description="After a successful change you will be signed out so you can sign in with the new password."
          actions={
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
              <KeyRound className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            </span>
          }
        />
        <form
          onSubmit={(e) => void onChangePassword(e)}
          className="mt-5 max-w-md space-y-4"
          noValidate
        >
          <PasswordField
            id={currentPasswordId}
            label="Current password"
            value={currentPassword}
            onChange={setCurrentPassword}
            autoComplete="current-password"
            disabled={passwordBusy}
          />
          <PasswordField
            id={newPasswordId}
            label="New password"
            value={newPassword}
            onChange={setNewPassword}
            autoComplete="new-password"
            disabled={passwordBusy}
            hint="At least 10 characters."
          />
          <PasswordField
            id={confirmPasswordId}
            label="Confirm new password"
            value={confirmPassword}
            onChange={setConfirmPassword}
            autoComplete="new-password"
            disabled={passwordBusy}
          />
          {passwordError ? <Alert tone="error">{passwordError}</Alert> : null}
          <Button type="submit" variant="primary" disabled={passwordBusy}>
            {passwordBusy ? "Updating..." : "Change password"}
          </Button>
        </form>
      </Panel>
    </div>
  );
}
