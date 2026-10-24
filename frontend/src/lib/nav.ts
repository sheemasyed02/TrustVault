import type { UserRole } from "@/lib/api";

export interface NavItem {
  label: string;
  href: string;
  /** When false, shown for role awareness but not a working screen yet. */
  available: boolean;
  /** Optional sidebar section heading (UI grouping only). */
  section?: string;
}

export interface NavSection {
  id: string;
  label: string | null;
  items: NavItem[];
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
      { label: "Dashboard", href: "/dashboard", available: true, section: "Overview" },
      { label: "My Documents", href: "/documents", available: true, section: "Documents" },
      { label: "Shared", href: "/shared", available: true, section: "Documents" },
      { label: "Activity", href: "/activity", available: true, section: "Documents" },
      { label: "Upload", href: "/documents/upload", available: true, section: "Documents" },
      { label: "Profile", href: "/profile", available: true, section: "Account" },
    ];
  }

  if (role === "VIEWER") {
    return [
      { label: "Dashboard", href: "/dashboard", available: true, section: "Overview" },
      { label: "Shared", href: "/shared", available: true, section: "Overview" },
      {
        label: "Request owner",
        href: "/request-owner",
        available: true,
        section: "Account",
      },
      { label: "Profile", href: "/profile", available: true, section: "Account" },
    ];
  }

  // ADMIN — administration only (document content still requires ownership/grant).
  return [
    { label: "Dashboard", href: "/admin", available: true, section: "Overview" },
    { label: "Users", href: "/admin/users", available: true, section: "Users" },
    {
      label: "Owner requests",
      href: "/admin/promotions",
      available: true,
      section: "Users",
    },
    {
      label: "Views",
      href: "/admin/audit/views",
      available: true,
      section: "Audit",
    },
    { label: "Audit Logs", href: "/admin/audit", available: true, section: "Audit" },
    {
      label: "Audit Integrity",
      href: "/admin/audit/integrity",
      available: true,
      section: "Audit",
    },
    { label: "Profile", href: "/profile", available: true, section: "Account" },
  ];
}

/** Group flat role nav into labeled sections for the sidebar. */
export function getNavSectionsForRole(role: UserRole): NavSection[] {
  const items = getNavItemsForRole(role);
  const order: string[] = [];
  const map = new Map<string, NavItem[]>();

  for (const item of items) {
    const key = item.section ?? "Menu";
    if (!map.has(key)) {
      map.set(key, []);
      order.push(key);
    }
    map.get(key)!.push(item);
  }

  return order.map((id) => ({
    id,
    label: id === "Overview" ? null : id,
    items: map.get(id) ?? [],
  }));
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

export interface ShellPageMeta {
  title: string;
  subtitle?: string;
  crumbs: { label: string; href?: string }[];
}

/**
 * Resolve light shell header context from the current path.
 * Does not invent features — titles mirror existing routes/nav labels.
 */
export function getShellPageMeta(
  pathname: string,
  role: UserRole,
): ShellPageMeta {
  const items = getNavItemsForRole(role);
  const exact = items.find((item) => item.href === pathname);
  if (exact) {
    return {
      title: exact.label,
      subtitle: exact.section && exact.section !== "Overview" ? exact.section : undefined,
      crumbs: [{ label: exact.label }],
    };
  }

  if (pathname.startsWith("/documents/") && pathname !== "/documents/upload") {
    return {
      title: "Document",
      subtitle: "Details and access",
      crumbs: [
        { label: "My Documents", href: "/documents" },
        { label: "Document" },
      ],
    };
  }

  if (pathname.startsWith("/admin/users/")) {
    return {
      title: "User",
      subtitle: "Account management",
      crumbs: [
        { label: "Users", href: "/admin/users" },
        { label: "User" },
      ],
    };
  }

  // Nested path under a known nav prefix (e.g. future children).
  const nested = [...items]
    .filter((item) => item.href !== "/" && pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0];

  if (nested) {
    return {
      title: nested.label,
      subtitle: nested.section,
      crumbs: [{ label: nested.label, href: nested.href }],
    };
  }

  return {
    title: "TrustVault",
    crumbs: [{ label: "Workspace" }],
  };
}
