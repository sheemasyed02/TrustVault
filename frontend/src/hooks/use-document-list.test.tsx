import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/auth-provider";
import { useDocumentList } from "@/hooks/use-document-list";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function Probe({ title, ownerId }: { title: string; ownerId?: string }) {
  const list = useDocumentList({
    title,
    owner_id: ownerId,
    page_size: 20,
  });
  return (
    <div>
      <p data-testid="status">{list.status}</p>
      <p data-testid="titles">{list.results.map((d) => d.title).join("|")}</p>
      <p data-testid="error">{list.errorMessage ?? ""}</p>
    </div>
  );
}

function Authed({ children }: { children: React.ReactNode }) {
  const { login, status } = useAuth();
  if (status !== "authenticated") {
    return (
      <button type="button" onClick={() => void login("a@b.com", "x")}>
        go
      </button>
    );
  }
  return <>{children}</>;
}

function mockAuthApis() {
  vi.spyOn(api, "loginRequest").mockResolvedValue({
    access_token: "tok",
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
}

describe("useDocumentList", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("loads documents from the API client with owner filter", async () => {
    mockAuthApis();
    const listSpy = vi.spyOn(api, "listDocumentsRequest").mockResolvedValue({
      results: [],
      page: 1,
      page_size: 20,
      total: 0,
      total_pages: 0,
    });

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <Probe title="" ownerId="00000000-0000-0000-0000-000000000001" />
        </Authed>
      </AuthProvider>,
    );
    await user.click(screen.getByRole("button", { name: "go" }));

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("empty");
    });
    expect(listSpy.mock.calls.some((call) => call[1]?.owner_id)).toBe(true);
  });

  it("ignores stale responses when a newer search finishes first", async () => {
    mockAuthApis();

    let resolveSlow: (value: api.DocumentListResponse) => void = () => undefined;
    const slow = new Promise<api.DocumentListResponse>((resolve) => {
      resolveSlow = resolve;
    });

    vi.spyOn(api, "listDocumentsRequest").mockImplementation((_token, params) => {
      if (params?.title === "old") return slow;
      return Promise.resolve({
        results: [
          {
            id: "22222222-2222-2222-2222-222222222222",
            title: "new-hit",
            category: "HR",
            owner: {
              id: "00000000-0000-0000-0000-000000000001",
              name: "Owner",
              email: "owner@example.com",
            },
            mime_type: "application/pdf",
            file_size: 1,
            created_at: "2026-10-21T12:00:00+00:00",
          },
        ],
        page: 1,
        page_size: 20,
        total: 1,
        total_pages: 1,
      });
    });

    function SearchHarness() {
      const [title, setTitle] = useState("old");
      return (
        <div>
          <button type="button" onClick={() => setTitle("new")}>
            search-new
          </button>
          <Probe title={title} />
        </div>
      );
    }

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <SearchHarness />
        </Authed>
      </AuthProvider>,
    );
    await user.click(screen.getByRole("button", { name: "go" }));
    await user.click(screen.getByRole("button", { name: "search-new" }));

    await waitFor(() => {
      expect(screen.getByTestId("titles")).toHaveTextContent("new-hit");
    });

    resolveSlow({
      results: [
        {
          id: "33333333-3333-3333-3333-333333333333",
          title: "stale-old",
          category: "HR",
          owner: {
            id: "00000000-0000-0000-0000-000000000001",
            name: "Owner",
            email: "owner@example.com",
          },
          mime_type: "application/pdf",
          file_size: 1,
          created_at: "2026-10-21T12:00:00+00:00",
        },
      ],
      page: 1,
      page_size: 20,
      total: 1,
      total_pages: 1,
    });

    await new Promise((r) => setTimeout(r, 40));
    expect(screen.getByTestId("titles")).toHaveTextContent("new-hit");
    expect(screen.getByTestId("titles")).not.toHaveTextContent("stale-old");
  });

  it("clears session on 401 from the list API", async () => {
    mockAuthApis();
    vi.spyOn(api, "listDocumentsRequest").mockRejectedValue(
      new api.ApiError(401, "Not authenticated"),
    );

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <Probe title="" />
        </Authed>
      </AuthProvider>,
    );
    await user.click(screen.getByRole("button", { name: "go" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "go" })).toBeInTheDocument();
    });
  });
});
