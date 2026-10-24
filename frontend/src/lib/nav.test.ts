import { describe, expect, it } from "vitest";

import {
  getNavItemsForRole,
  getNavSectionsForRole,
  getPostLoginPath,
  getShellPageMeta,
  isNavItemActive,
} from "@/lib/nav";

describe("getPostLoginPath", () => {
  it("routes each role to the correct home", () => {
    expect(getPostLoginPath("ADMIN")).toBe("/admin");
    expect(getPostLoginPath("OWNER")).toBe("/dashboard");
    expect(getPostLoginPath("VIEWER")).toBe("/dashboard");
  });
});

describe("getNavItemsForRole", () => {
  it("gives owners document tools plus Profile", () => {
    const items = getNavItemsForRole("OWNER");
    const labels = items.map((item) => item.label);
    expect(labels).toEqual([
      "Dashboard",
      "My Documents",
      "Shared",
      "Activity",
      "Upload",
      "Profile",
    ]);
    expect(labels).not.toContain("Manage Users");
    expect(items.every((item) => item.available)).toBe(true);
    expect(items.find((i) => i.label === "Shared")?.href).toBe("/shared");
    expect(items.find((i) => i.label === "Activity")?.href).toBe("/activity");
  });

  it("gives viewers dashboard, shared docs, owner request, and Profile", () => {
    const labels = getNavItemsForRole("VIEWER").map((item) => item.label);
    expect(labels).toEqual([
      "Dashboard",
      "Shared",
      "Request owner",
      "Profile",
    ]);
    expect(labels).not.toContain("Upload");
    expect(labels).not.toContain("Users");
    expect(getNavItemsForRole("VIEWER").find((i) => i.label === "Shared")?.href).toBe(
      "/shared",
    );
  });

  it("shows admin screens plus Profile for ADMIN role", () => {
    const adminLabels = getNavItemsForRole("ADMIN").map((item) => item.label);
    expect(adminLabels).toContain("Dashboard");
    expect(adminLabels).toContain("Users");
    expect(adminLabels).toContain("Audit Logs");
    expect(adminLabels).toContain("Audit Integrity");
    expect(adminLabels).toContain("Profile");
    expect(adminLabels).not.toContain("Upload");
    const integrity = getNavItemsForRole("ADMIN").find(
      (i) => i.label === "Audit Integrity",
    );
    expect(integrity?.href).toBe("/admin/audit/integrity");
    expect(getNavItemsForRole("OWNER").map((i) => i.label)).not.toContain("Users");
    expect(getNavItemsForRole("VIEWER").map((i) => i.label)).not.toContain("Users");
  });
});

describe("getNavSectionsForRole", () => {
  it("groups owner links without adding or removing routes", () => {
    const sections = getNavSectionsForRole("OWNER");
    const hrefs = sections.flatMap((s) => s.items.map((i) => i.href));
    expect(hrefs).toEqual([
      "/dashboard",
      "/documents",
      "/shared",
      "/activity",
      "/documents/upload",
      "/profile",
    ]);
    expect(sections.map((s) => s.id)).toEqual([
      "Overview",
      "Documents",
      "Account",
    ]);
  });
});

describe("getShellPageMeta", () => {
  it("resolves titles and document breadcrumbs from existing routes", () => {
    expect(getShellPageMeta("/dashboard", "OWNER").title).toBe("Dashboard");
    expect(getShellPageMeta("/shared", "VIEWER").title).toBe("Shared");
    const detail = getShellPageMeta(
      "/documents/11111111-1111-1111-1111-111111111111",
      "OWNER",
    );
    expect(detail.title).toBe("Document");
    expect(detail.crumbs[0]).toEqual({
      label: "My Documents",
      href: "/documents",
    });
  });
});

describe("isNavItemActive", () => {
  it("keeps Audit Logs and Audit Integrity as distinct active states", () => {
    expect(isNavItemActive("/admin", "/admin")).toBe(true);
    expect(isNavItemActive("/admin/users", "/admin")).toBe(false);
    expect(isNavItemActive("/admin/users", "/admin/users")).toBe(true);
    expect(isNavItemActive("/admin/audit", "/admin/audit")).toBe(true);
    expect(isNavItemActive("/admin/audit/integrity", "/admin/audit")).toBe(
      false,
    );
    expect(
      isNavItemActive("/admin/audit/integrity", "/admin/audit/integrity"),
    ).toBe(true);
    expect(isNavItemActive("/documents/abc", "/documents")).toBe(true);
    expect(isNavItemActive("/profile", "/profile")).toBe(true);
  });
});
