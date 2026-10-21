import { describe, expect, it } from "vitest";

import { getNavItemsForRole } from "@/lib/nav";

describe("getNavItemsForRole", () => {
  it("shows owner document options without claiming admin APIs", () => {
    const labels = getNavItemsForRole("OWNER").map((item) => item.label);
    expect(labels).toContain("Dashboard");
    expect(labels).toContain("My Documents");
    expect(labels).toContain("Upload");
    expect(labels).not.toContain("Admin");
  });

  it("shows viewer shared option", () => {
    const labels = getNavItemsForRole("VIEWER").map((item) => item.label);
    expect(labels).toEqual(["Dashboard", "Shared with me"]);
  });

  it("limits admin to dashboard until admin APIs exist in the UI", () => {
    expect(getNavItemsForRole("ADMIN").map((i) => i.label)).toEqual([
      "Dashboard",
    ]);
  });
});
