import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminUsersPage from "@/app/(app)/admin/users/page";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const handleUnauthorized = vi.hoisted(() => () => false);

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    status: "authenticated",
    accessToken: "tok",
    user: {
      id: "00000000-0000-0000-0000-000000000099",
      name: "Admin",
      email: "admin@example.com",
      role: "ADMIN",
    },
  }),
  useHandleUnauthorized: () => handleUnauthorized,
}));

describe("AdminUsersPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads users from the API and confirms before deactivating", async () => {
    vi.spyOn(api, "listAdminUsersRequest").mockResolvedValue({
      results: [
        {
          id: "11111111-1111-1111-1111-111111111111",
          name: "Viewer",
          email: "viewer@example.com",
          role: "VIEWER",
          is_active: true,
          created_at: "2026-10-21T12:00:00+00:00",
          updated_at: "2026-10-21T12:00:00+00:00",
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
      total_pages: 1,
    });
    const patch = vi.spyOn(api, "patchAdminUserStatusRequest").mockResolvedValue({
      id: "11111111-1111-1111-1111-111111111111",
      name: "Viewer",
      email: "viewer@example.com",
      role: "VIEWER",
      is_active: false,
      created_at: "2026-10-21T12:00:00+00:00",
      updated_at: "2026-10-21T13:00:00+00:00",
    });

    const user = userEvent.setup();
    render(<AdminUsersPage />);

    expect(await screen.findByText("viewer@example.com")).toBeInTheDocument();
    expect(api.listAdminUsersRequest).toHaveBeenCalled();
    expect(screen.getByRole("link", { name: /View profile/i })).toHaveAttribute(
      "href",
      "/admin/users/11111111-1111-1111-1111-111111111111",
    );

    await user.click(screen.getByRole("button", { name: /^Deactivate$/i }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      /Deactivate this account/i,
    );
    expect(patch).not.toHaveBeenCalled();

    const confirmButtons = screen.getAllByRole("button", {
      name: /^Deactivate$/i,
    });
    await user.click(confirmButtons[confirmButtons.length - 1]!);
    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith(
        "tok",
        "11111111-1111-1111-1111-111111111111",
        false,
      );
    });
  });

  it("shows API error state without fabricating users", async () => {
    vi.spyOn(api, "listAdminUsersRequest").mockRejectedValue(
      new api.ApiError(503, "Service unavailable"),
    );
    render(<AdminUsersPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Service unavailable/i,
    );
    // Help text may mention @example.com fixtures; the table must stay empty.
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("viewer@example.com")).not.toBeInTheDocument();
  });
});
