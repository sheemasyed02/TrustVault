"use client";

import { LoaderCircle, Mail } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthPasswordField } from "@/components/auth-password-field";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { getPostLoginPath } from "@/lib/nav";

export function LoginEntry() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status, login, errorMessage, clearError, user } = useAuth();
  const emailId = useId();
  const passwordId = useId();
  const errorId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const passwordChanged = searchParams.get("passwordChanged") === "1";

  const isSubmitting = status === "loading";

  useEffect(() => {
    if (status === "authenticated" && user) {
      router.replace(getPostLoginPath(user.role));
    }
  }, [status, user, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearError();
    setValidationError(null);
    setAttempted(true);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setValidationError("Enter your work email and password.");
      return;
    }

    await login(trimmedEmail, password);
  }

  const displayError = validationError ?? errorMessage;
  const emailInvalid = attempted && !email.trim();
  const passwordInvalid = attempted && !password;

  return (
    <section
      aria-labelledby="sign-in-heading"
      className="rounded-[var(--radius)] border border-border bg-surface p-6 shadow-[var(--shadow)] sm:p-8"
    >
      <h1
        id="sign-in-heading"
        className="text-2xl font-semibold tracking-tight text-foreground"
      >
        Sign in
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted">
        Enter your work email and password to continue.
      </p>

      {passwordChanged ? (
        <p
          role="status"
          className="mt-4 rounded-[0.625rem] border border-success/30 bg-[color-mix(in_srgb,var(--success)_10%,white)] px-3 py-2 text-sm text-success"
        >
          Password updated. Sign in with your new password.
        </p>
      ) : null}

      <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
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
              autoComplete="username"
              required
              value={email}
              disabled={isSubmitting}
              aria-invalid={emailInvalid || undefined}
              onChange={(event) => {
                setEmail(event.target.value);
                if (validationError) setValidationError(null);
                if (errorMessage) clearError();
              }}
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
          autoComplete="current-password"
          required
          value={password}
          disabled={isSubmitting}
          invalid={passwordInvalid}
          placeholder="••••••••"
          onChange={(event) => {
            setPassword(event.target.value);
            if (validationError) setValidationError(null);
            if (errorMessage) clearError();
          }}
        />

        {displayError ? (
          <p
            id={errorId}
            role="alert"
            className="rounded-[0.625rem] border border-danger/30 bg-[color-mix(in_srgb,var(--danger)_8%,white)] px-3 py-2 text-sm text-danger"
          >
            {displayError}
          </p>
        ) : null}

        <Button
          type="submit"
          variant="primary"
          disabled={isSubmitting}
          aria-busy={isSubmitting}
          aria-describedby={displayError ? errorId : undefined}
          className="w-full"
        >
          {isSubmitting ? (
            <>
              <LoaderCircle
                className="h-4 w-4 animate-spin"
                strokeWidth={1.75}
                aria-hidden
              />
              Signing in…
            </>
          ) : (
            "Sign in"
          )}
        </Button>
      </form>

      <p className="mt-5 text-center text-sm text-muted">
        New here?{" "}
        <Link
          href="/signup"
          className="font-semibold text-accent-strong underline decoration-accent/40 underline-offset-2 transition-colors duration-[180ms] hover:text-accent"
        >
          Create a Viewer account
        </Link>
      </p>
      <p className="mt-3 text-center text-xs leading-5 text-muted">
        Access tokens stay in this browser tab only. Refreshing signs you out.
      </p>
    </section>
  );
}
