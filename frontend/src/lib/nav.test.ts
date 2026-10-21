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

  it("does not invent admin-only screens", () => {
    const labels = getNavItemsForRole("ADMIN").map((item) => item.label);
    expect(labels).not.toContain("Admin");
    expect(labels).toContain("Dashboard");
  });
});
