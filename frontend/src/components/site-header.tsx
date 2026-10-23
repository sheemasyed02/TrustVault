"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { BrandLogo } from "@/components/brand-logo";

export function SiteHeader() {
  const { status } = useAuth();
  const isAuthenticated = status === "authenticated";

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 px-6 py-4 md:px-10">
      <div className="flex items-center gap-3">
        <Link
          href={isAuthenticated ? "/dashboard" : "/"}
          className="flex items-center gap-2.5 font-display text-2xl tracking-tight text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent md:gap-3 md:text-3xl"
        >
          <BrandLogo size="sm" decorative />
          TrustVault
        </Link>
        <p className="hidden text-sm text-muted sm:block">
          Secure document sharing
        </p>
      </div>
      {!isAuthenticated ? (
        <p className="rounded-md bg-accent-soft px-3 py-1 text-xs font-medium text-accent-strong">
          Sign in required
        </p>
      ) : null}
    </header>
  );
}
