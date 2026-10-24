"use client";

import { LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { AuthPasswordField } from "@/components/auth-password-field";
import { Button, buttonClassName } from "@/components/ui/button";
import { ApiError, resetPasswordRequest } from "@/lib/api";

const MIN_PASSWORD_LEN = 10;
const MAX_PASSWORD_LEN = 128;

const INVALID_LINK_MESSAGE =
  "This password reset link is invalid or has expired. Request a new one.";

/**
 * Reset form. The one-time token stays in the query string only for this page
 * load — it is never written to localStorage/sessionStorage/cookies, never
 * rendered in the UI, and never logged. Page metadata uses referrer=no-referrer.
 */
export function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const passwordId = useId();
  const confirmId = useId();
  const errorId = useId();

  const token = (searchParams.get("token") ?? "").trim();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [linkRejected, setLinkRejected] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || message) return;

    setError(null);
    setAttempted(true);

    if (!token) {
      setError(INVALID_LINK_MESSAGE);
      setLinkRejected(true);
      return;
    }
    if (password.length < MIN_PASSWORD_LEN) {
      setError(`Password must be at least ${MIN_PASSWORD_LEN} characters.`);
      return;
    }
    if (password.length > MAX_PASSWORD_LEN) {
      setError(`Password must be at most ${MAX_PASSWORD_LEN} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("New password and confirmation do not match.");
      return;
    }

    setBusy(true);
    try {
      const result = await resetPasswordRequest({
        token,
        new_password: password,
        confirm_password: confirm,
      });
      setPassword("");
      setConfirm("");
      setMessage(result.message);
      // Drop the token from the address bar after a successful consume.
      router.replace("/reset-password", { scroll: false });
    } catch (err) {
      const detail =
        err instanceof ApiError
          ? err.detail
          : "Unable to reset your password. Try again.";
      setError(detail);
      if (
        err instanceof ApiError &&
        (err.status === 400 ||
          detail.toLowerCase().includes("invalid") ||
          detail.toLowerCase().includes("expired"))
      ) {
        setLinkRejected(true);
        router.replace("/reset-password", { scroll: false });
      }
    } finally {
      setBusy(false);
    }
  }

  const passwordInvalid = attempted && password.length < MIN_PASSWORD_LEN;
  const confirmInvalid =
    attempted && (confirm.length === 0 || password !== confirm);
  const showInvalidLink = (!token || linkRejected) && !message;

  if (showInvalidLink) {
    return (
      <section aria-labelledby="reset-password-heading" className="w-full">
        <h1
          id="reset-password-heading"
          className="font-accent text-3xl font-semibold tracking-tight text-foreground"
        >
          Reset password
        </h1>
        <p
          role="alert"
          className="mt-4 rounded-[0.625rem] border border-danger/30 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-3 py-2 text-sm text-danger"
        >
          {error ?? INVALID_LINK_MESSAGE}
        </p>
        <div className="mt-6 flex flex-col gap-3">
          <Link
            href="/forgot-password"
            className={buttonClassName({
              variant: "primary",
              className: "w-full min-h-11 text-base",
            })}
          >
            Request a new reset link
          </Link>
          <Link
            href="/"
            className={buttonClassName({
              variant: "secondary",
              className:
                "w-full min-h-11 border-accent/45 text-base text-accent-strong hover:border-accent hover:bg-accent-soft",
            })}
          >
            Back to Sign In
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section aria-labelledby="reset-password-heading" className="w-full">
      <h1
        id="reset-password-heading"
        className="font-accent text-3xl font-semibold tracking-tight text-foreground"
      >
        Reset password
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted">
        Choose a new password for your TrustVault account. This link can be used
        only once.
      </p>

      {message ? (
        <>
          <p
            role="status"
            className="mt-6 rounded-[0.625rem] border border-success/30 bg-[color-mix(in_srgb,var(--success)_10%,white)] px-3 py-2 text-sm text-success"
          >
            {message}
          </p>
          <div className="mt-6">
            <Link
              href="/?passwordChanged=1"
              className={buttonClassName({
                variant: "primary",
                className: "w-full min-h-11 text-base",
              })}
            >
              Sign in with new password
            </Link>
          </div>
        </>
      ) : (
        <form className="mt-7 space-y-4" onSubmit={onSubmit} noValidate>
          <AuthPasswordField
            id={passwordId}
            label="New password"
            name="new_password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LEN}
            maxLength={MAX_PASSWORD_LEN}
            value={password}
            disabled={busy}
            invalid={passwordInvalid}
            placeholder="••••••••"
            hint={`At least ${MIN_PASSWORD_LEN} characters (max ${MAX_PASSWORD_LEN}).`}
            onChange={(event) => {
              setPassword(event.target.value);
              if (error) setError(null);
            }}
          />

          <AuthPasswordField
            id={confirmId}
            label="Confirm new password"
            name="confirm_password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LEN}
            maxLength={MAX_PASSWORD_LEN}
            value={confirm}
            disabled={busy}
            invalid={confirmInvalid}
            placeholder="••••••••"
            onChange={(event) => {
              setConfirm(event.target.value);
              if (error) setError(null);
            }}
          />

          {error ? (
            <p
              id={errorId}
              role="alert"
              className="rounded-[0.625rem] border border-danger/30 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-3 py-2 text-sm text-danger"
            >
              {error}
            </p>
          ) : null}

          <Button
            type="submit"
            variant="primary"
            disabled={busy}
            aria-busy={busy}
            aria-describedby={error ? errorId : undefined}
            className="mt-1 w-full min-h-11 text-base"
          >
            {busy ? (
              <>
                <LoaderCircle
                  className="h-4 w-4 animate-spin"
                  strokeWidth={1.75}
                  aria-hidden
                />
                Resetting password…
              </>
            ) : (
              "Reset Password"
            )}
          </Button>
        </form>
      )}

      {!message ? (
        <p className="mt-6 text-center text-sm text-muted">
          <Link
            href="/forgot-password"
            className="font-semibold text-accent-strong transition-colors duration-[180ms] hover:text-accent"
          >
            Request a new link
          </Link>
          {" · "}
          <Link
            href="/"
            className="font-semibold text-accent-strong transition-colors duration-[180ms] hover:text-accent"
          >
            Sign in
          </Link>
        </p>
      ) : null}
    </section>
  );
}
