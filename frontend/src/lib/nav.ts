import type { UserRole } from "@/lib/api";

export interface NavItem {
  label: string;
  href: string;
  /** When false, shown for role awareness but not a working screen yet. */
  available: boolean;
}

/**
 * Post-login home path by platform role (UI routing only).
 * Backend authorization remains the security boundary.
 */
export function getPostLoginPath(role: UserRole): string {
  if (role === "ADMIN") return "/admin";
  if (role === "VIEWER") return "/shared";
  return "/dashboard";
}

/**
 * Role-aware navigation for UI only. Backend authorization remains authoritative.
 */
export function getNavItemsForRole(role: UserRole): NavItem[] {
  if (role === "OWNER") {
    return [
      { label: "Dashboard", href: "/dashboard", available: true },
      { label: "My Documents", href: "/documents", available: true },
      { label: "Shared with me", href: "/shared", available: true },
      { label: "Upload", href: "/documents/upload", available: true },
    ];
  }

  if (role === "VIEWER") {
    return [
      { label: "Shared with me", href: "/shared", available: true },
    ];
  }

  // ADMIN — administration only (document content still requires ownership/grant).
  return [
    { label: "Overview", href: "/admin", available: true },
    { label: "Users", href: "/admin/users", available: true },
    { label: "Audit Logs", href: "/admin/audit", available: true },
    { label: "Audit Integrity", href: "/admin/audit?focus=integrity", available: true },
  ];
}

/** Highlight the current nav item without activating parent Overview for child admin routes. */
export function isNavItemActive(pathname: string, href: string): boolean {
  const pathOnly = href.split("?")[0] ?? href;
  if (pathOnly === "/admin") {
    return pathname === "/admin";
  }
  if (pathname === pathOnly) return true;
  if (pathOnly === "/dashboard") return false;
  return pathname.startsWith(`${pathOnly}/`);
}
