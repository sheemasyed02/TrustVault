import { describe, expect, it } from "vitest";

import { getNavItemsForRole, getPostLoginPath, isNavItemActive } from "@/lib/nav";

describe("getPostLoginPath", () => {
  it("routes each role to the correct home", () => {
    expect(getPostLoginPath("ADMIN")).toBe("/admin");
    expect(getPostLoginPath("OWNER")).toBe("/dashboard");
    expect(getPostLoginPath("VIEWER")).toBe("/shared");
  });
});

describe("getNavItemsForRole", () => {
  it("gives owners dashboard, documents, shared, and upload", () => {
    const items = getNavItemsForRole("OWNER");
    const labels = items.map((item) => item.label);
    expect(labels).toEqual([
      "Dashboard",
      "My Documents",
      "Shared with me",
      "Upload",
    ]);
    expect(items.every((item) => item.available)).toBe(true);
  });

  it("gives viewers shared documents and owner request", () => {
    const labels = getNavItemsForRole("VIEWER").map((item) => item.label);
    expect(labels).toEqual(["Shared with me", "Request owner access"]);
    expect(labels).not.toContain("Upload");
    expect(labels).not.toContain("Admin");
  });

  it("shows admin screens only for ADMIN role", () => {
    const adminLabels = getNavItemsForRole("ADMIN").map((item) => item.label);
    expect(adminLabels).toEqual([
      "Overview",
      "Users",
      "Owner requests",
      "Audit Logs",
      "Audit Integrity",
    ]);
    expect(getNavItemsForRole("OWNER").map((i) => i.label)).not.toContain(
      "Overview",
    );
    expect(getNavItemsForRole("VIEWER").map((i) => i.label)).not.toContain(
      "Users",
    );
  });
});

describe("isNavItemActive", () => {
  it("does not mark Overview active on nested admin routes", () => {
    expect(isNavItemActive("/admin", "/admin")).toBe(true);
    expect(isNavItemActive("/admin/users", "/admin")).toBe(false);
    expect(isNavItemActive("/admin/users", "/admin/users")).toBe(true);
    expect(isNavItemActive("/documents/abc", "/documents")).toBe(true);
  });
});
