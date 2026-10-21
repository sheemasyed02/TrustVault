import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/auth-provider";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function AuthProbe() {
  const { status, user, accessToken, errorMessage, login, logout } = useAuth();
  return (
    <div data-testid="auth-probe">
      <p data-testid="status">{status}</p>
      <p data-testid="user">{user?.email ?? "none"}</p>
      <p data-testid="token">{accessToken ? "present" : "absent"}</p>
      <p data-testid="error">{errorMessage ?? ""}</p>
      <button
        type="button"
        onClick={() => void login("owner@example.com", "password")}
      >
        Login
      </button>
      <button type="button" onClick={() => logout()}>
        Logout
      </button>
    </div>
  );
}

function renderAuthProbe() {
  return render(
    <AuthProvider>
      <AuthProbe />
    </AuthProvider>,
  );
}

function probe() {
  return within(screen.getByTestId("auth-probe"));
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it("logs in, fetches /users/me, and keeps the token out of storage", async () => {
    const setItemLocal = vi.spyOn(Storage.prototype, "setItem");
    vi.spyOn(api, "loginRequest").mockResolvedValue({
      access_token: "memory-token",
      token_type: "bearer",
      expires_at: "2026-10-21T12:00:00+00:00",
      expires_in: 1800,
    });
    vi.spyOn(api, "getCurrentUserRequest").mockResolvedValue({
      id: "00000000-0000-0000-0000-000000000001",
      name: "Owner",
      email: "owner@example.com",
      role: "OWNER",
      is_active: true,
      created_at: "2026-10-21T12:00:00+00:00",
      updated_at: "2026-10-21T12:00:00+00:00",
    });

    const user = userEvent.setup();
    renderAuthProbe();

    await user.click(probe().getByRole("button", { name: "Login" }));

    await waitFor(() => {
      expect(probe().getByTestId("status")).toHaveTextContent("authenticated");
    });
    expect(probe().getByTestId("user")).toHaveTextContent("owner@example.com");
    expect(probe().getByTestId("token")).toHaveTextContent("present");
    expect(api.getCurrentUserRequest).toHaveBeenCalledWith("memory-token");

    const storageWrites = setItemLocal.mock.calls.map((call) => String(call[1]));
    expect(storageWrites.join(" ")).not.toContain("memory-token");
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("access_token")).toBeNull();
  });

  it("shows a safe error on invalid login and stays unauthenticated", async () => {
    vi.spyOn(api, "loginRequest").mockRejectedValue(
      new api.ApiError(401, api.GENERIC_LOGIN_ERROR),
    );

    const user = userEvent.setup();
    renderAuthProbe();

    await user.click(probe().getByRole("button", { name: "Login" }));

    await waitFor(() => {
      expect(probe().getByTestId("error")).toHaveTextContent(
        api.GENERIC_LOGIN_ERROR,
      );
    });
    expect(probe().getByTestId("status")).toHaveTextContent("unauthenticated");
    expect(probe().getByTestId("token")).toHaveTextContent("absent");
  });

  it("does not authenticate when /users/me fails after login", async () => {
    vi.spyOn(api, "loginRequest").mockResolvedValue({
      access_token: "memory-token",
      token_type: "bearer",
      expires_at: "2026-10-21T12:00:00+00:00",
      expires_in: 1800,
    });
    vi.spyOn(api, "getCurrentUserRequest").mockRejectedValue(
      new api.ApiError(401, "Not authenticated"),
    );

    const user = userEvent.setup();
    renderAuthProbe();

    await user.click(probe().getByRole("button", { name: "Login" }));

    await waitFor(() => {
      expect(probe().getByTestId("status")).toHaveTextContent("unauthenticated");
    });
    expect(probe().getByTestId("token")).toHaveTextContent("absent");
    expect(probe().getByTestId("user")).toHaveTextContent("none");
  });

  it("logout clears the in-memory session", async () => {
    vi.spyOn(api, "loginRequest").mockResolvedValue({
      access_token: "memory-token",
      token_type: "bearer",
      expires_at: "2026-10-21T12:00:00+00:00",
      expires_in: 1800,
    });
    vi.spyOn(api, "getCurrentUserRequest").mockResolvedValue({
      id: "00000000-0000-0000-0000-000000000001",
      name: "Owner",
      email: "owner@example.com",
      role: "OWNER",
      is_active: true,
      created_at: "2026-10-21T12:00:00+00:00",
      updated_at: "2026-10-21T12:00:00+00:00",
    });

    const user = userEvent.setup();
    renderAuthProbe();

    await user.click(probe().getByRole("button", { name: "Login" }));
    await waitFor(() => {
      expect(probe().getByTestId("status")).toHaveTextContent("authenticated");
    });

    await user.click(probe().getByRole("button", { name: "Logout" }));
    expect(probe().getByTestId("status")).toHaveTextContent("unauthenticated");
    expect(probe().getByTestId("token")).toHaveTextContent("absent");
    expect(probe().getByTestId("user")).toHaveTextContent("none");
  });

  it("shows a useful error on API network failure", async () => {
    vi.spyOn(api, "loginRequest").mockRejectedValue(
      new api.ApiError(0, "Unable to reach the TrustVault API. Check that the backend is running."),
    );

    const user = userEvent.setup();
    renderAuthProbe();

    await user.click(probe().getByRole("button", { name: "Login" }));

    await waitFor(() => {
      expect(probe().getByTestId("error")).toHaveTextContent(
        "Unable to reach the TrustVault API",
      );
    });
  });
});
