import type { UserRole } from "@/lib/api";

export interface NavItem {
  label: string;
  href: string;
  /** When false, shown for role awareness but not a working screen yet. */
  available: boolean;
}

/**
 * Role-aware navigation for UI only. Backend authorization remains authoritative.
 * Admin management APIs are not exposed in the UI until those routes exist.
 */
export function getNavItemsForRole(role: UserRole): NavItem[] {
  const dashboard: NavItem = {
    label: "Dashboard",
    href: "/dashboard",
    available: true,
  };

  if (role === "OWNER") {
    return [
      dashboard,
      { label: "My Documents", href: "/dashboard", available: false },
      { label: "Upload", href: "/dashboard", available: false },
    ];
  }

  if (role === "VIEWER") {
    return [
      dashboard,
      { label: "Shared with me", href: "/dashboard", available: false },
    ];
  }

  // ADMIN — no admin audit/user-management screens exist yet.
  return [dashboard];
}
