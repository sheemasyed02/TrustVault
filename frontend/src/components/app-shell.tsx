"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { BrandLogo } from "@/components/brand-logo";
import { Button } from "@/components/ui/button";
import { getNavItemsForRole, isNavItemActive } from "@/lib/nav";

function SidebarNav({
  menuOpen,
  setMenuOpen,
}: {
  menuOpen: boolean;
  setMenuOpen: (open: boolean) => void;
}) {
  const { user } = useAuth();
  const pathname = usePathname();
  if (!user) return null;

  const items = getNavItemsForRole(user.role);

  return (
    <nav
      id="app-sidebar-nav"
      aria-label="Workspace"
      className={`${menuOpen ? "mt-4 flex" : "hidden"} flex-col gap-0.5 md:mt-5 md:flex`}
    >
      {items.map((item) => {
        const active = isNavItemActive(pathname, item.href);
        return (
          <Link
            key={item.label}
            href={item.href}
            onClick={() => setMenuOpen(false)}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
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
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!user) return null;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-5 px-4 py-5 md:flex-row md:gap-8 md:px-8 md:py-8">
      <aside className="md:w-56 md:shrink-0">
        <div className="flex items-center justify-between gap-3 md:block">
          <div className="flex items-center gap-2.5">
            <BrandLogo size="sm" decorative />
            <div>
              <p className="font-display text-xl text-foreground">TrustVault</p>
              <p className="mt-0.5 text-xs text-muted">{user.role} workspace</p>
            </div>
          </div>
          <Button
            size="sm"
            variant="secondary"
            className="md:hidden"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="app-sidebar-nav"
          >
            {menuOpen ? "Close" : "Menu"}
          </Button>
        </div>

        <SidebarNav menuOpen={menuOpen} setMenuOpen={setMenuOpen} />

        <div className="mt-5 hidden rounded-xl border border-border bg-surface p-4 text-sm shadow-[var(--shadow-sm)] md:block">
          <p className="font-medium text-foreground">{user.name}</p>
          <p className="mt-1 break-all text-xs text-muted">{user.email}</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3 w-full"
            onClick={() => logout()}
          >
            Sign out
          </Button>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <div className="mb-4 flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3 shadow-[var(--shadow-sm)] md:hidden">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">
              {user.name}
            </p>
            <p className="text-xs text-muted">{user.role}</p>
          </div>
          <Button size="sm" variant="secondary" onClick={() => logout()}>
            Sign out
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}
