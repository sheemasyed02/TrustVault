"use client";

import Link from "next/link";
import { type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";

/**
 * UI gate for administrator screens. Backend ADMIN checks remain mandatory.
 */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, status } = useAuth();

  if (status === "loading") {
    return (
      <div className="px-1 py-8" role="status" aria-live="polite">
        <p className="text-sm text-muted">Checking your session…</p>
      </div>
    );
  }

  if (!user || user.role !== "ADMIN") {
    return (
      <div
        role="alert"
        className="rounded-xl border border-danger/30 bg-danger/5 px-5 py-6 text-sm text-danger"
      >
        <h1 className="font-semibold text-2xl text-foreground">Forbidden</h1>
        <p className="mt-2 text-muted">
          Administrator access is required for this page. Your role does not
          grant permission to manage users or inspect the audit trail.
        </p>
        <p className="mt-4">
          <Link
            href="/dashboard"
            className="font-semibold text-accent-strong hover:underline"
          >
            ← Back to dashboard
          </Link>
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
