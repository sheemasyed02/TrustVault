"use client";

import { useAuth } from "@/components/auth-provider";

/**
 * Authenticated landing shell only. Document list/upload screens are later tasks.
 */
export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="mx-auto w-full max-w-3xl flex-1 px-6 py-12 md:px-10 md:py-16">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
        Signed in
      </p>
      <h1 className="mt-3 font-display text-3xl tracking-tight text-foreground md:text-4xl">
        Welcome, {user?.name}
      </h1>
      <p className="mt-4 max-w-xl text-base leading-7 text-muted">
        You are authenticated as <strong className="font-medium text-foreground">{user?.role}</strong>.
        Document browsing and upload screens will connect here in a later task.
        Until then, use Sign out when you are finished — logout clears this
        browser session but does not revoke the JWT on the server.
      </p>
      <dl className="mt-8 grid gap-4 rounded-xl border border-border bg-surface p-5 text-sm shadow-[var(--shadow)] sm:grid-cols-2">
        <div>
          <dt className="text-muted">Email</dt>
          <dd className="mt-1 font-medium text-foreground">{user?.email}</dd>
        </div>
        <div>
          <dt className="text-muted">Role</dt>
          <dd className="mt-1 font-medium text-foreground">{user?.role}</dd>
        </div>
      </dl>
    </div>
  );
}
