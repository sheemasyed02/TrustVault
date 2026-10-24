import { Suspense } from "react";

import { AuthSplitLayout } from "@/components/auth-split-layout";
import { LoginEntry } from "@/components/login-entry";
import { Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  return (
    <AuthSplitLayout
      welcome="Your data. Your control."
      support="Accessed only by the right people."
      marketingLabel="TrustVault sign-in"
    >
      <Suspense
        fallback={
          <div className="w-full" role="status">
            <Skeleton className="h-9 w-48" />
            <Skeleton className="mt-3 h-4 w-64" />
            <Skeleton className="mt-8 h-11 w-full" />
            <Skeleton className="mt-3 h-11 w-full" />
            <Skeleton className="mt-6 h-11 w-full" />
            <p className="mt-4 text-sm text-muted">Loading sign-in…</p>
          </div>
        }
      >
        <LoginEntry />
      </Suspense>
    </AuthSplitLayout>
  );
}
