"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { getNavItemsForRole } from "@/lib/nav";

export function AppNav() {
  const { user, logout } = useAuth();
  if (!user) return null;

  const items = getNavItemsForRole(user.role);

  return (
    <div className="flex flex-wrap items-center gap-3 md:gap-4">
      <nav aria-label="Application" className="flex flex-wrap items-center gap-1">
        {items.map((item) =>
          item.available ? (
            <Link
              key={item.label}
              href={item.href}
              className="rounded-md px-2.5 py-1.5 text-sm font-medium text-foreground hover:bg-accent-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {item.label}
            </Link>
          ) : (
            <span
              key={item.label}
              title="Coming in a later task"
              className="cursor-default rounded-md px-2.5 py-1.5 text-sm text-muted"
            >
              {item.label}
            </span>
          ),
        )}
      </nav>
      <div className="hidden h-5 w-px bg-border sm:block" aria-hidden />
      <p className="text-xs text-muted sm:text-sm">
        <span className="font-medium text-foreground">{user.name}</span>
        <span className="mx-1.5 text-border">·</span>
        <span>{user.role}</span>
      </p>
      <button
        type="button"
        onClick={() => logout()}
        className="rounded-md border border-border bg-white px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-accent-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:text-sm"
      >
        Sign out
      </button>
    </div>
  );
}
