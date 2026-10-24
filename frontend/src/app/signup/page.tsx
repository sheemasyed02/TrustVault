"use client";

import { LoaderCircle, Mail, UserPlus, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { AuthPasswordField } from "@/components/auth-password-field";
import { AuthSplitLayout } from "@/components/auth-split-layout";
import { AuthTextField } from "@/components/auth-text-field";
import { Button, buttonClassName } from "@/components/ui/button";
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
      welcome="Your data. Your control."
      support="Accessed only by the right people."
      marketingLabel="TrustVault sign-up"
    >
      <section aria-labelledby="sign-up-heading" className="w-full">
        <h1
          id="sign-up-heading"
          className="font-accent text-3xl font-semibold tracking-tight text-foreground"
        >
          Create New Account
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Register as a Viewer. Owner and Administrator roles are assigned by
          TrustVault administrators.
        </p>

        <form className="mt-7 space-y-4" onSubmit={onSubmit} noValidate>
          <AuthTextField
            id={nameId}
            label="Full name"
            name="name"
            type="text"
            autoComplete="name"
            required
            value={name}
            disabled={busy}
            invalid={nameInvalid}
            placeholder="Jane Doe"
            leadingIcon={<UserRound className="h-4 w-4" strokeWidth={1.75} />}
            onChange={(e) => setName(e.target.value)}
          />

          <AuthTextField
            id={emailId}
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            disabled={busy}
            invalid={emailInvalid}
            placeholder="you@example.com"
            leadingIcon={<Mail className="h-4 w-4" strokeWidth={1.75} />}
            onChange={(e) => setEmail(e.target.value)}
          />

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
            placeholder="••••••••"
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
            placeholder="••••••••"
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
            className="mt-1 w-full min-h-11 text-base"
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
              <>
                <UserPlus className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                Create Viewer Account
              </>
            )}
          </Button>
        </form>

        <div className="relative my-5 text-center" role="separator" aria-label="or">
          <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
          <span className="relative bg-background px-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            or
          </span>
        </div>

        <Link
          href="/"
          className={buttonClassName({
            variant: "secondary",
            className:
              "w-full min-h-11 border-accent/45 text-base text-accent-strong hover:border-accent hover:bg-accent-soft",
          })}
        >
          Sign In
        </Link>
      </section>
    </AuthSplitLayout>
  );
}
