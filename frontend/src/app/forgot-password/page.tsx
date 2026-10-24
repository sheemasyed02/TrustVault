"use client";

import { LoaderCircle, Mail } from "lucide-react";
import Link from "next/link";
import { useId, useState, type FormEvent } from "react";

import { AuthSplitLayout } from "@/components/auth-split-layout";
import { AuthTextField } from "@/components/auth-text-field";
import { Button, buttonClassName } from "@/components/ui/button";
import { ApiError, forgotPasswordRequest } from "@/lib/api";

function isValidEmail(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > 320) return false;
  // Practical client check; server validates with EmailStr.
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed);
}

export default function ForgotPasswordPage() {
  const emailId = useId();
  const errorId = useId();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setMessage(null);
    setAttempted(true);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError("Enter the email address for your TrustVault account.");
      return;
    }
    if (!isValidEmail(trimmedEmail)) {
      setError("Enter a valid email address.");
      return;
    }

    setBusy(true);
    try {
      const result = await forgotPasswordRequest(trimmedEmail);
      setMessage(result.message);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Unable to send a reset link. Try again in a moment.",
      );
    } finally {
      setBusy(false);
    }
  }

  const emailInvalid =
    attempted && (!email.trim() || !isValidEmail(email.trim()));

  return (
    <AuthSplitLayout
      welcome="Reset with care."
      support="We only email a link when an eligible account matches."
      marketingLabel="TrustVault forgot password"
    >
      <section aria-labelledby="forgot-password-heading" className="w-full">
        <h1
          id="forgot-password-heading"
          className="font-accent text-3xl font-semibold tracking-tight text-foreground"
        >
          Forgot password
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Enter your account email. If an eligible TrustVault account exists,
          we will send a reset link. The message is the same whether or not the
          address is registered.
        </p>

        <form className="mt-7 space-y-4" onSubmit={onSubmit} noValidate>
          <AuthTextField
            id={emailId}
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            disabled={busy || Boolean(message)}
            invalid={emailInvalid}
            placeholder="you@example.com"
            leadingIcon={<Mail className="h-4 w-4" strokeWidth={1.75} />}
            onChange={(event) => {
              setEmail(event.target.value);
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
          {message ? (
            <p
              role="status"
              className="rounded-[0.625rem] border border-success/30 bg-[color-mix(in_srgb,var(--success)_10%,white)] px-3 py-2 text-sm text-success"
            >
              {message}
            </p>
          ) : null}

          <Button
            type="submit"
            variant="primary"
            disabled={busy || Boolean(message)}
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
                Sending reset link…
              </>
            ) : (
              "Send Reset Link"
            )}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted">
          Remembered your password?{" "}
          <Link
            href="/"
            className="font-semibold text-accent-strong transition-colors duration-[180ms] hover:text-accent"
          >
            Sign in
          </Link>
        </p>

        <div className="mt-5">
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
    </AuthSplitLayout>
  );
}
