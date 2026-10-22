import { describe, expect, it } from "vitest";

import { getNavItemsForRole, getPostLoginPath, isNavItemActive } from "@/lib/nav";

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
      "Shared Documents",
      "Document Activity",
      "Upload",
      "Profile",
    ]);
    expect(labels).not.toContain("Manage Users");
    expect(items.every((item) => item.available)).toBe(true);
  });

  it("gives viewers dashboard, shared docs, owner request, and Profile", () => {
    const labels = getNavItemsForRole("VIEWER").map((item) => item.label);
    expect(labels).toEqual([
      "Dashboard",
      "Shared Documents",
      "Request owner access",
      "Profile",
    ]);
    expect(labels).not.toContain("Upload");
    expect(labels).not.toContain("Manage Users");
  });

  it("shows admin screens plus Profile for ADMIN role", () => {
    const adminLabels = getNavItemsForRole("ADMIN").map((item) => item.label);
    expect(adminLabels).toContain("Dashboard");
    expect(adminLabels).toContain("Manage Users");
    expect(adminLabels).toContain("Audit Logs");
    expect(adminLabels).toContain("Audit Integrity");
    expect(adminLabels).toContain("Profile");
    expect(adminLabels).not.toContain("Upload");
    const integrity = getNavItemsForRole("ADMIN").find(
      (i) => i.label === "Audit Integrity",
    );
    expect(integrity?.href).toBe("/admin/audit/integrity");
    expect(getNavItemsForRole("OWNER").map((i) => i.label)).not.toContain(
      "Manage Users",
    );
    expect(getNavItemsForRole("VIEWER").map((i) => i.label)).not.toContain(
      "Manage Users",
    );
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
