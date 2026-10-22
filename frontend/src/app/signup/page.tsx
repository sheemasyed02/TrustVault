"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { ApiError, registerRequest } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();
  const confirmId = useId();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

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

  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-10 px-6 py-12 md:grid-cols-[1.15fr_0.85fr] md:px-10 md:py-16">
      <section className="max-w-xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Create account
        </p>
        <h1 className="mt-4 font-display text-4xl leading-tight tracking-tight text-foreground md:text-5xl">
          TrustVault
        </h1>
        <p className="mt-4 max-w-md text-base leading-7 text-muted md:text-lg">
          Public registration creates a Viewer account. You cannot choose Owner
          or Administrator during signup — request owner access after signing in
          if you need to upload documents.
        </p>
        <ul className="mt-8 space-y-3 text-sm leading-6 text-muted">
          <li>Passwords are hashed on the server; they never appear in responses.</li>
          <li>Role is assigned by TrustVault — client-supplied roles are ignored.</li>
          <li>Administrators are provisioned only through the secure seed process.</li>
        </ul>
      </section>

      <section className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow)] backdrop-blur md:p-8">
        <h2 className="font-display text-2xl tracking-tight text-foreground">
          Sign up
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted">
          Already registered?{" "}
          <Link href="/" className="font-semibold text-accent-strong underline">
            Sign in
          </Link>
          .
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
          <div className="space-y-2">
            <label htmlFor={nameId} className="block text-sm font-medium">
              Full name
            </label>
            <input
              id={nameId}
              name="name"
              type="text"
              autoComplete="name"
              required
              value={name}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-70"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor={emailId} className="block text-sm font-medium">
              Work email
            </label>
            <input
              id={emailId}
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              disabled={busy}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-70"
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
              autoComplete="new-password"
              required
              minLength={10}
              value={password}
              disabled={busy}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-70"
            />
            <p className="text-xs text-muted">At least 10 characters.</p>
          </div>
          <div className="space-y-2">
            <label htmlFor={confirmId} className="block text-sm font-medium">
              Confirm password
            </label>
            <input
              id={confirmId}
              name="confirm"
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              value={confirm}
              disabled={busy}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-70"
            />
          </div>

          {error ? (
            <p
              role="alert"
              className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger"
            >
              {error}
            </p>
          ) : null}
          {message ? (
            <p role="status" className="text-sm text-accent-strong">
              {message}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            aria-busy={busy}
            className="w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? "Creating account…" : "Create Viewer account"}
          </button>
        </form>
      </section>
    </div>
  );
}
