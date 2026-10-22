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
  if (role === "VIEWER") return "/dashboard";
  return "/dashboard";
}

/**
 * Role-aware navigation for UI only. Backend authorization remains authoritative.
 * Only routes the role can actually use are listed.
 */
export function getNavItemsForRole(role: UserRole): NavItem[] {
  if (role === "OWNER") {
    return [
      { label: "Dashboard", href: "/dashboard", available: true },
      { label: "My Documents", href: "/documents", available: true },
      { label: "Shared Documents", href: "/shared", available: true },
      { label: "Document Activity", href: "/activity", available: true },
      { label: "Upload", href: "/documents/upload", available: true },
      { label: "Profile", href: "/profile", available: true },
    ];
  }

  if (role === "VIEWER") {
    return [
      { label: "Dashboard", href: "/dashboard", available: true },
      { label: "Shared Documents", href: "/shared", available: true },
      { label: "Request owner access", href: "/request-owner", available: true },
      { label: "Profile", href: "/profile", available: true },
    ];
  }

  // ADMIN — administration only (document content still requires ownership/grant).
  return [
    { label: "Dashboard", href: "/admin", available: true },
    { label: "Manage Users", href: "/admin/users", available: true },
    { label: "Owner requests", href: "/admin/promotions", available: true },
    { label: "Document views", href: "/admin/audit/views", available: true },
    { label: "Audit Logs", href: "/admin/audit", available: true },
    { label: "Audit Integrity", href: "/admin/audit/integrity", available: true },
    { label: "Profile", href: "/profile", available: true },
  ];
}

/** Highlight the current nav item without activating parent Overview for child admin routes. */
export function isNavItemActive(pathname: string, href: string): boolean {
  const pathOnly = href.split("?")[0] ?? href;
  if (pathOnly === "/admin") {
    return pathname === "/admin";
  }
  // Prefer the more specific integrity route over /admin/audit prefix matching.
  if (pathOnly === "/admin/audit") {
    return pathname === "/admin/audit";
  }
  if (pathname === pathOnly) return true;
  if (pathOnly === "/dashboard") return false;
  return pathname.startsWith(`${pathOnly}/`);
}
