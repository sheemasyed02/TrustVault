"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { BrandLogo } from "@/components/brand-logo";

const AUTH_ROUTES = new Set(["/", "/signup"]);

export function SiteHeader() {
  const { status } = useAuth();
  const pathname = usePathname();
  const isAuthenticated = status === "authenticated";

  /* Authenticated chrome lives in AppShell. Auth pages use AuthSplitLayout. */
  if (isAuthenticated || AUTH_ROUTES.has(pathname)) return null;

  return (
    <header className="border-b border-border bg-surface/80 px-6 py-4 backdrop-blur-sm md:px-10">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2.5 text-xl font-semibold tracking-tight text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent md:gap-3 md:text-2xl"
          >
            <BrandLogo size="sm" decorative />
            TrustVault
          </Link>
          <p className="hidden font-accent text-sm text-muted sm:block">
            Confidential, by design
          </p>
        </div>
        <p className="rounded-[0.5rem] bg-accent-soft px-3 py-1 text-xs font-medium text-accent-strong">
          Sign in required
        </p>
      </div>
    </header>
  );
}
