"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { getNavItemsForRole } from "@/lib/nav";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!user) return null;

  const items = getNavItemsForRole(user.role);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 md:flex-row md:px-8 md:py-8">
      <aside className="md:w-56 md:shrink-0">
        <div className="flex items-center justify-between gap-3 md:block">
          <div>
            <p className="font-display text-xl text-foreground">TrustVault</p>
            <p className="mt-1 text-xs text-muted">Signed in workspace</p>
          </div>
          <button
            type="button"
            className="rounded-md border border-border px-3 py-1.5 text-sm md:hidden"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="app-sidebar-nav"
          >
            Menu
          </button>
        </div>

        <nav
          id="app-sidebar-nav"
          aria-label="Workspace"
          className={`${menuOpen ? "mt-4 flex" : "hidden"} flex-col gap-1 md:mt-6 md:flex`}
        >
          {items.map((item) => {
            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.label}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className={`rounded-md px-3 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  active
                    ? "bg-accent-soft text-accent-strong"
                    : "text-foreground hover:bg-white/70"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-6 hidden rounded-xl border border-border bg-surface p-4 text-sm md:block">
          <p className="font-medium text-foreground">{user.name}</p>
          <p className="mt-1 break-all text-muted">{user.email}</p>
          <p className="mt-2 text-xs uppercase tracking-wide text-accent-strong">
            {user.role}
          </p>
          <button
            type="button"
            onClick={() => logout()}
            className="mt-4 w-full rounded-md border border-border bg-white px-3 py-2 text-sm font-semibold hover:bg-accent-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Sign out
          </button>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <div className="mb-4 flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3 md:hidden">
          <div>
            <p className="text-sm font-medium text-foreground">{user.name}</p>
            <p className="text-xs text-muted">{user.role}</p>
          </div>
          <button
            type="button"
            onClick={() => logout()}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold"
          >
            Sign out
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
