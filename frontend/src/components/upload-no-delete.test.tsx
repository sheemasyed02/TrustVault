import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/auth-provider";
import { UploadDocumentForm } from "@/components/upload-document-form";
import * as api from "@/lib/api";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push, prefetch: vi.fn() }),
}));

function Authed({ children }: { children: ReactNode }) {
  const { login, status } = useAuth();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void login("owner@example.com", "password").then(() => setReady(true));
  }, [login]);
  if (!ready || status !== "authenticated") return <p>booting</p>;
  return children;
}

describe("upload must not delete", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    push.mockReset();
    vi.spyOn(api, "loginRequest").mockResolvedValue({
      access_token: "tok",
      token_type: "bearer",
      expires_at: "2099-01-01T00:00:00+00:00",
      expires_in: 3600,
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
  });

  afterEach(() => {
    cleanup();
  });

  it("successful upload does not call deleteDocumentRequest or send DELETE", async () => {
    const deleteSpy = vi.spyOn(api, "deleteDocumentRequest");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    vi.spyOn(api, "uploadDocumentRequest").mockResolvedValue({
      id: "11111111-1111-1111-1111-111111111111",
      title: "Kept",
      category: "Finance",
      description: null,
      owner: {
        id: "00000000-0000-0000-0000-000000000001",
        name: "Owner",
        email: "owner@example.com",
      },
      mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      file_size: 12,
      sha256_checksum: "abc",
      created_at: "2026-10-21T12:00:00+00:00",
      updated_at: "2026-10-21T12:00:00+00:00",
      your_access: "OWNER",
    });

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <UploadDocumentForm />
        </Authed>
      </AuthProvider>,
    );

    await screen.findByRole("button", { name: /upload document/i });
    await user.type(screen.getByLabelText(/^Title$/i), "Kept");
    await user.type(screen.getByLabelText(/^Category$/i), "Finance");
    await user.upload(
      screen.getByLabelText(/^File$/i),
      new File(["PK"], "kept.docx", {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
    );
    await user.click(screen.getByRole("button", { name: /upload document/i }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(
        "/documents/11111111-1111-1111-1111-111111111111",
      );
    });
    expect(deleteSpy).not.toHaveBeenCalled();
    expect(screen.queryByTestId("upload-error")).toBeNull();
    // No raw DELETE fetch should have been issued by the upload path.
    const deleteCalls = fetchMock.mock.calls.filter((call) => {
      const init = call[1] as RequestInit | undefined;
      return String(init?.method ?? "").toUpperCase() === "DELETE";
    });
    expect(deleteCalls).toHaveLength(0);
  });
});
