import type { UserRole } from "@/lib/api";

export interface NavItem {
  label: string;
  href: string;
  /** When false, shown for role awareness but not a working screen yet. */
  available: boolean;
}

/**
 * Role-aware navigation for UI only. Backend authorization remains authoritative.
 */
export function getNavItemsForRole(role: UserRole): NavItem[] {
  const common: NavItem[] = [
    { label: "Dashboard", href: "/dashboard", available: true },
    { label: "My Documents", href: "/documents", available: true },
    { label: "Shared with me", href: "/shared", available: true },
  ];

  if (role === "OWNER") {
    return [
      ...common,
      {
        label: "Upload",
        href: "/documents/upload",
        available: true,
      },
    ];
  }

  if (role === "VIEWER") {
    return common;
  }

  // ADMIN — overview + user management + audit (server still enforces ADMIN).
  return [
    ...common,
    { label: "Admin", href: "/admin", available: true },
    { label: "Users", href: "/admin/users", available: true },
    { label: "Audit log", href: "/admin/audit", available: true },
  ];
}
