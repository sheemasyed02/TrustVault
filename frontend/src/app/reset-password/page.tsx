import { Suspense } from "react";

import { AuthSplitLayout } from "@/components/auth-split-layout";
import { ResetPasswordForm } from "@/components/reset-password-form";
import { Skeleton } from "@/components/ui/skeleton";

export default function ResetPasswordPage() {
  return (
    <AuthSplitLayout
      welcome="A fresh start."
      support="Set a strong password known only to you."
      marketingLabel="TrustVault reset password"
    >
      <Suspense
        fallback={
          <div className="w-full" role="status">
            <Skeleton className="h-9 w-52" />
            <Skeleton className="mt-3 h-4 w-72" />
            <Skeleton className="mt-8 h-11 w-full" />
            <Skeleton className="mt-3 h-11 w-full" />
            <Skeleton className="mt-6 h-11 w-full" />
            <p className="mt-4 text-sm text-muted">Loading reset form…</p>
          </div>
        }
      >
        <ResetPasswordForm />
      </Suspense>
    </AuthSplitLayout>
  );
}
