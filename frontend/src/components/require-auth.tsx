"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";

export function RequireAuth({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div
        className="flex flex-1 items-center justify-center px-6 py-16"
        role="status"
        aria-live="polite"
      >
        <p className="text-sm text-muted">Checking your session…</p>
      </div>
    );
  }

  if (status !== "authenticated") {
    // Avoid flashing protected content while redirecting.
    return (
      <div
        className="flex flex-1 items-center justify-center px-6 py-16"
        role="status"
        aria-live="polite"
      >
        <p className="text-sm text-muted">Redirecting to sign in…</p>
      </div>
    );
  }

  return <>{children}</>;
}
