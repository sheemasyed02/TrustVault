"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
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
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="block text-sm font-medium">
          {label}
        </label>
        <button
          type="button"
          className="text-xs font-semibold text-accent-strong hover:underline"
          onClick={() => setVisible((v) => !v)}
        >
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
        className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-70"
      />
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
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
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Account
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
          Profile
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Your personal details from the authenticated session. You cannot change
          your role or account status here.
        </p>
      </header>

      <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
        <h2 className="font-display text-xl text-foreground">
          Personal information
        </h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Email</dt>
            <dd className="mt-1 break-all text-sm text-foreground">{user.email}</dd>
            <p className="mt-1 text-xs text-muted">
              Email is your login identity and cannot be changed here.
            </p>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Role</dt>
            <dd className="mt-1 text-sm font-semibold text-accent-strong">
              {user.role}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">
              Account status
            </dt>
            <dd className="mt-1 text-sm text-foreground">
              {user.is_active ? "Active" : "Inactive"}
            </dd>
          </div>
          <div>
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
          <label htmlFor={nameId} className="block text-sm">
            <span className="mb-1 block font-medium">Full name</span>
            <input
              id={nameId}
              name="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              minLength={2}
              maxLength={255}
              disabled={profileBusy}
              className="w-full max-w-md rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-70"
            />
          </label>
          {profileError ? (
            <p role="alert" className="text-sm text-danger">
              {profileError}
            </p>
          ) : null}
          {profileMessage ? (
            <p role="status" className="text-sm text-accent-strong">
              {profileMessage}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={profileBusy || name.trim() === user.name}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
          >
            {profileBusy ? "Saving…" : "Save name"}
          </button>
        </form>
      </section>

      <section className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]">
        <h2 className="font-display text-xl text-foreground">Security</h2>
        <p className="mt-1 text-sm text-muted">
          Change your password. After a successful change you will be signed out
          so you can sign in with the new password.
        </p>
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
          {passwordError ? (
            <p role="alert" className="text-sm text-danger">
              {passwordError}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={passwordBusy}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
          >
            {passwordBusy ? "Updating…" : "Change password"}
          </button>
        </form>
      </section>
    </div>
  );
}
