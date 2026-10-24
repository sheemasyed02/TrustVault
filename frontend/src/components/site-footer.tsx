"use client";

import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth-provider";

const AUTH_ROUTES = new Set(["/", "/signup"]);

export function SiteFooter() {
  const { status } = useAuth();
  const pathname = usePathname();

  if (status === "authenticated" || AUTH_ROUTES.has(pathname)) return null;

  return (
    <footer className="border-t border-border bg-accent-soft/40 px-6 py-4 text-sm text-muted md:px-10">
      <div className="mx-auto max-w-6xl">
        <p>
          Document access is enforced by the TrustVault API. Hiding a menu item
          is not authorization.
        </p>
      </div>
    </footer>
  );
}
