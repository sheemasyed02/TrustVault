"use client";

import { LoaderCircle, Mail, UserPlus } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthPasswordField } from "@/components/auth-password-field";
import { AuthTextField } from "@/components/auth-text-field";
import { useAuth } from "@/components/auth-provider";
import { Button, buttonClassName } from "@/components/ui/button";
import { getPostLoginPath } from "@/lib/nav";

const REMEMBER_EMAIL_KEY = "tv-remember-email";

export function LoginEntry() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status, login, errorMessage, clearError, user } = useAuth();
  const emailId = useId();
  const passwordId = useId();
  const rememberId = useId();
  const errorId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [forgotHint, setForgotHint] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const passwordChanged = searchParams.get("passwordChanged") === "1";

  const isSubmitting = status === "loading";

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(REMEMBER_EMAIL_KEY);
      if (saved) {
        setEmail(saved);
        setRememberMe(true);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (status === "authenticated" && user) {
      router.replace(getPostLoginPath(user.role));
    }
  }, [status, user, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearError();
    setValidationError(null);
    setForgotHint(false);
    setAttempted(true);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setValidationError("Enter your work email and password.");
      return;
    }

    try {
      if (rememberMe) {
        window.localStorage.setItem(REMEMBER_EMAIL_KEY, trimmedEmail);
      } else {
        window.localStorage.removeItem(REMEMBER_EMAIL_KEY);
      }
    } catch {
      /* ignore */
    }

    await login(trimmedEmail, password);
  }

  const displayError = validationError ?? errorMessage;
  const emailInvalid = attempted && !email.trim();
  const passwordInvalid = attempted && !password;

  return (
    <section aria-labelledby="sign-in-heading" className="w-full">
      <h1
        id="sign-in-heading"
        className="font-accent text-3xl font-semibold tracking-tight text-foreground"
      >
        Welcome Back
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted">
        Sign in to your TrustVault account
      </p>

      {passwordChanged ? (
        <p
          role="status"
          className="mt-4 rounded-[0.625rem] border border-success/30 bg-[color-mix(in_srgb,var(--success)_10%,white)] px-3 py-2 text-sm text-success"
        >
          Password updated. Sign in with your new password.
        </p>
      ) : null}

      <form className="mt-7 space-y-4" onSubmit={onSubmit} noValidate>
        <AuthTextField
          id={emailId}
          label="Email"
          name="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          disabled={isSubmitting}
          invalid={emailInvalid}
          placeholder="you@example.com"
          leadingIcon={<Mail className="h-4 w-4" strokeWidth={1.75} />}
          onChange={(event) => {
            setEmail(event.target.value);
            if (validationError) setValidationError(null);
            if (errorMessage) clearError();
          }}
        />

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

        <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5">
          <label
            htmlFor={rememberId}
            className="inline-flex cursor-pointer items-center gap-2 text-sm text-muted"
          >
            <input
              id={rememberId}
              name="remember"
              type="checkbox"
              checked={rememberMe}
              disabled={isSubmitting}
              onChange={(event) => setRememberMe(event.target.checked)}
              className="h-4 w-4 rounded border-border text-accent accent-[var(--accent)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            />
            Remember me
          </label>
          <button
            type="button"
            className="text-sm font-semibold text-accent-strong transition-colors duration-[180ms] hover:text-accent"
            onClick={() => setForgotHint(true)}
          >
            Forgot password?
          </button>
        </div>

        {forgotHint ? (
          <p
            role="status"
            className="rounded-[0.625rem] border border-border bg-accent-soft/60 px-3 py-2 text-sm text-muted"
          >
            Ask a TrustVault administrator to reset your password.
          </p>
        ) : null}

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
          className="mt-1 w-full min-h-11 text-base"
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
            "Sign In"
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
        href="/signup"
        className={buttonClassName({
          variant: "secondary",
          className:
            "w-full min-h-11 border-accent/45 text-base text-accent-strong hover:border-accent hover:bg-accent-soft",
        })}
      >
        <UserPlus className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        Create New Account
      </Link>

      <p className="mt-5 text-center text-xs leading-5 text-muted">
        Access tokens stay in this browser tab only. Refreshing signs you out.
      </p>
    </section>
  );
}
