"use client";

import { LoaderCircle, Mail, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { AuthPasswordField } from "@/components/auth-password-field";
import { AuthSplitLayout } from "@/components/auth-split-layout";
import { Button } from "@/components/ui/button";
import { ApiError, registerRequest } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();
  const confirmId = useId();
  const errorId = useId();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setAttempted(true);

    const trimmedName = name.trim();
    const trimmedEmail = email.trim();
    if (trimmedName.length < 2) {
      setError("Enter your full name (at least 2 characters).");
      return;
    }
    if (!trimmedEmail || !trimmedEmail.includes("@")) {
      setError("Enter a valid work email address.");
      return;
    }
    if (password.length < 10) {
      setError("Password must be at least 10 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Password and confirmation do not match.");
      return;
    }

    setBusy(true);
    try {
      const result = await registerRequest({
        name: trimmedName,
        email: trimmedEmail,
        password,
      });
      setMessage(result.message);
      window.setTimeout(() => router.push("/"), 1200);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Unable to create an account. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const nameInvalid = attempted && name.trim().length < 2;
  const emailInvalid =
    attempted && (!email.trim() || !email.trim().includes("@"));
  const passwordInvalid = attempted && password.length < 10;
  const confirmInvalid =
    attempted && (confirm.length === 0 || password !== confirm);

  return (
    <AuthSplitLayout
      welcome="Join as a Viewer."
      support="Registration creates a Viewer account. Owner and Administrator roles are assigned by TrustVault administrators."
      marketingLabel="TrustVault sign-up"
    >
      <section
        aria-labelledby="sign-up-heading"
        className="rounded-[var(--radius)] border border-border bg-surface p-6 shadow-[var(--shadow)] sm:p-8"
      >
        <h1
          id="sign-up-heading"
          className="text-2xl font-semibold tracking-tight text-foreground"
        >
          Create account
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Viewer access only. You cannot choose Owner or Administrator here.
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
          <div>
            <label htmlFor={nameId} className="tv-label">
              Full name
            </label>
            <div className="relative">
              <UserRound
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
                strokeWidth={1.75}
                aria-hidden
              />
              <input
                id={nameId}
                name="name"
                type="text"
                autoComplete="name"
                required
                value={name}
                disabled={busy}
                aria-invalid={nameInvalid || undefined}
                onChange={(e) => setName(e.target.value)}
                className={`tv-input pl-9 ${
                  nameInvalid ? "border-danger focus:border-danger" : ""
                }`}
              />
            </div>
          </div>

          <div>
            <label htmlFor={emailId} className="tv-label">
              Work email
            </label>
            <div className="relative">
              <Mail
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
                strokeWidth={1.75}
                aria-hidden
              />
              <input
                id={emailId}
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                disabled={busy}
                aria-invalid={emailInvalid || undefined}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className={`tv-input pl-9 ${
                  emailInvalid ? "border-danger focus:border-danger" : ""
                }`}
              />
            </div>
          </div>

          <AuthPasswordField
            id={passwordId}
            label="Password"
            name="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={password}
            disabled={busy}
            invalid={passwordInvalid}
            hint="At least 10 characters."
            onChange={(e) => setPassword(e.target.value)}
          />

          <AuthPasswordField
            id={confirmId}
            label="Confirm password"
            name="confirm"
            autoComplete="new-password"
            required
            minLength={10}
            value={confirm}
            disabled={busy}
            invalid={confirmInvalid}
            onChange={(e) => setConfirm(e.target.value)}
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
            disabled={busy}
            aria-busy={busy}
            aria-describedby={error ? errorId : undefined}
            className="w-full"
          >
            {busy ? (
              <>
                <LoaderCircle
                  className="h-4 w-4 animate-spin"
                  strokeWidth={1.75}
                  aria-hidden
                />
                Creating account…
              </>
            ) : (
              "Create Viewer account"
            )}
          </Button>
        </form>

        <p className="mt-5 text-center text-sm text-muted">
          Already registered?{" "}
          <Link
            href="/"
            className="font-semibold text-accent-strong underline decoration-accent/40 underline-offset-2 transition-colors duration-[180ms] hover:text-accent"
          >
            Sign in
          </Link>
        </p>
      </section>
    </AuthSplitLayout>
  );
}
