import { Suspense } from "react";

import { AuthSplitLayout } from "@/components/auth-split-layout";
import { LoginEntry } from "@/components/login-entry";
import { Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  return (
    <AuthSplitLayout
      welcome="Welcome back."
      support="Sign in to open confidential documents protected by server-side permissions."
      marketingLabel="TrustVault sign-in"
    >
      <Suspense
        fallback={
          <div
            className="rounded-[var(--radius)] border border-border bg-surface p-6 shadow-[var(--shadow)] sm:p-8"
            role="status"
          >
            <Skeleton className="h-7 w-28" />
            <Skeleton className="mt-4 h-4 w-full" />
            <Skeleton className="mt-6 h-10 w-full" />
            <Skeleton className="mt-3 h-10 w-full" />
            <p className="mt-4 text-sm text-muted">Loading sign-in…</p>
          </div>
        }
      >
        <LoginEntry />
      </Suspense>
    </AuthSplitLayout>
  );
}
