"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";

export function LoginEntry() {
  const router = useRouter();
  const { status, login, errorMessage, clearError, user } = useAuth();
  const emailId = useId();
  const passwordId = useId();
  const errorId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const isSubmitting = status === "loading";

  useEffect(() => {
    if (status === "authenticated" && user) {
      router.replace("/dashboard");
    }
  }, [status, user, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearError();
    setValidationError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setValidationError("Enter your work email and password.");
      return;
    }

    await login(trimmedEmail, password);
  }

  const displayError = validationError ?? errorMessage;

  return (
    <section
      aria-labelledby="sign-in-heading"
      className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow)] backdrop-blur md:p-8"
    >
      <h2
        id="sign-in-heading"
        className="font-display text-2xl tracking-tight text-foreground"
      >
        Sign in
      </h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        Use your TrustVault account. Access tokens stay in memory for this
        browser tab — refreshing the page requires signing in again.
      </p>

      <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
        <div className="space-y-2">
          <label htmlFor={emailId} className="block text-sm font-medium">
            Work email
          </label>
          <input
            id={emailId}
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            disabled={isSubmitting}
            onChange={(event) => {
              setEmail(event.target.value);
              if (validationError) setValidationError(null);
              if (errorMessage) clearError();
            }}
            placeholder="you@company.com"
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm text-foreground outline-none ring-accent/40 placeholder:text-muted/80 focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-70"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={passwordId} className="block text-sm font-medium">
            Password
          </label>
          <input
            id={passwordId}
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            disabled={isSubmitting}
            onChange={(event) => {
              setPassword(event.target.value);
              if (validationError) setValidationError(null);
              if (errorMessage) clearError();
            }}
            placeholder="••••••••"
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm text-foreground outline-none ring-accent/40 placeholder:text-muted/80 focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-70"
          />
        </div>

        {displayError ? (
          <p
            id={errorId}
            role="alert"
            className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger"
          >
            {displayError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={isSubmitting}
          aria-busy={isSubmitting}
          aria-describedby={displayError ? errorId : undefined}
          className="w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-accent-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-70"
        >
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </section>
  );
}
