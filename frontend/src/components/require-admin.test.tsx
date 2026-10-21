import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequireAdmin } from "@/components/require-admin";

const authState = vi.hoisted(() => ({
  status: "authenticated" as string,
  user: {
    id: "1",
    name: "Owner",
    email: "owner@example.com",
    role: "OWNER",
  } as { id: string; name: string; email: string; role: string } | null,
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ status: authState.status, user: authState.user }),
}));

describe("RequireAdmin", () => {
  beforeEach(() => {
    authState.status = "authenticated";
    authState.user = {
      id: "1",
      name: "Owner",
      email: "owner@example.com",
      role: "OWNER",
    };
  });

  it("shows forbidden state for non-admin users", () => {
    render(
      <RequireAdmin>
        <p>Secret admin panel</p>
      </RequireAdmin>,
    );
    expect(screen.queryByText("Secret admin panel")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/Forbidden/i);
  });

  it("renders children for ADMIN users", () => {
    authState.user = {
      id: "2",
      name: "Admin",
      email: "admin@example.com",
      role: "ADMIN",
    };
    render(
      <RequireAdmin>
        <p>Secret admin panel</p>
      </RequireAdmin>,
    );
    expect(screen.getByText("Secret admin panel")).toBeInTheDocument();
  });
});
