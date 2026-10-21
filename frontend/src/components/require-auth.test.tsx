import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequireAuth } from "@/components/require-auth";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

const authState = vi.hoisted(() => ({
  status: "unauthenticated" as string,
}));

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ status: authState.status }),
}));

describe("RequireAuth", () => {
  beforeEach(() => {
    replace.mockClear();
    authState.status = "unauthenticated";
  });

  it("redirects unauthenticated users to login and hides private content", async () => {
    render(
      <RequireAuth>
        <p>Private dashboard content</p>
      </RequireAuth>,
    );

    expect(screen.queryByText("Private dashboard content")).not.toBeInTheDocument();
    expect(screen.getByText(/Redirecting to sign in/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/");
    });
  });

  it("renders children when authenticated", () => {
    authState.status = "authenticated";
    render(
      <RequireAuth>
        <p>Private dashboard content</p>
      </RequireAuth>,
    );
    expect(screen.getByText("Private dashboard content")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
