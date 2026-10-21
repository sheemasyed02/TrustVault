"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";

/** Upload form is intentionally not implemented in Task 13. */
export default function UploadPlaceholderPage() {
  const { user } = useAuth();

  if (user?.role !== "OWNER") {
    return (
      <div className="rounded-xl border border-border bg-surface p-6">
        <h1 className="font-display text-2xl">Upload unavailable</h1>
        <p className="mt-2 text-sm text-muted">
          Only OWNER accounts can upload. The API rejects other roles.
        </p>
        <Link href="/dashboard" className="mt-4 inline-block text-sm font-semibold text-accent-strong">
          Back to dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-dashed border-border bg-surface p-6">
      <h1 className="font-display text-2xl">Upload document</h1>
      <p className="mt-2 max-w-xl text-sm text-muted">
        The upload entry point is here for navigation, but the upload form is not
        built in this task. Backend <code>POST /documents</code> already exists
        and will be wired in a later task.
      </p>
      <Link
        href="/documents"
        className="mt-4 inline-block text-sm font-semibold text-accent-strong"
      >
        Go to My Documents
      </Link>
    </div>
  );
}
