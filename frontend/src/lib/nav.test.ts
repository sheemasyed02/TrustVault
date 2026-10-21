import { describe, expect, it } from "vitest";

import { getNavItemsForRole } from "@/lib/nav";

describe("getNavItemsForRole", () => {
  it("gives owners dashboard, documents, shared, and upload entry", () => {
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

  it("gives viewers dashboard, documents, and shared", () => {
    const labels = getNavItemsForRole("VIEWER").map((item) => item.label);
    expect(labels).toEqual(["Dashboard", "My Documents", "Shared with me"]);
  });

  it("shows admin screens only for ADMIN role", () => {
    const adminLabels = getNavItemsForRole("ADMIN").map((item) => item.label);
    expect(adminLabels).toEqual([
      "Dashboard",
      "My Documents",
      "Shared with me",
      "Admin",
      "Users",
      "Audit log",
    ]);
    expect(getNavItemsForRole("OWNER").map((i) => i.label)).not.toContain(
      "Admin",
    );
    expect(getNavItemsForRole("VIEWER").map((i) => i.label)).not.toContain(
      "Audit log",
    );
  });
});
