import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useDocumentActions } from "@/hooks/use-document-actions";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function AuthedActions() {
  const { login, status } = useAuth();
  const [booted, setBooted] = useState(false);
  const actions = useDocumentActions();

  useEffect(() => {
    void login("owner@example.com", "password").then(() => setBooted(true));
  }, [login]);

  if (!booted) return <p>booting</p>;

  return (
    <div>
      <p data-testid="auth">{status}</p>
      <button
        type="button"
        onClick={() =>
          void actions.download({
            id: "11111111-1111-1111-1111-111111111111",
            title: "Doc",
          })
        }
      >
        Download
      </button>
      <button
        type="button"
        onClick={() =>
          actions.requestDelete({
            id: "11111111-1111-1111-1111-111111111111",
            title: "Doc",
          })
        }
      >
        Delete
      </button>
      <p data-testid="error">{actions.actionError ?? ""}</p>
      <p data-testid="message">{actions.actionMessage ?? ""}</p>
      <ConfirmDialog
        open={actions.pendingDelete !== null}
        title="Delete?"
        description="Confirm delete"
        confirmLabel="Confirm delete"
        danger
        busy={actions.deleting}
        onCancel={actions.cancelDelete}
        onConfirm={() => void actions.confirmDelete()}
      />
    </div>
  );
}

describe("useDocumentActions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
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

  it("does not save a file when download fails", async () => {
    const createObjectURL = vi.fn(() => "blob:fake");
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(api, "downloadDocumentRequest").mockRejectedValue(
      new api.ApiError(403, "Forbidden"),
    );

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <AuthedActions />
      </AuthProvider>,
    );

    await screen.findByRole("button", { name: "Download" });
    await user.click(screen.getByRole("button", { name: "Download" }));

    await waitFor(() => {
      expect(screen.getByTestId("error")).toHaveTextContent(/forbidden/i);
    });
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(screen.getByTestId("message")).toHaveTextContent("");
  });

  it("delete requires confirmation and does not fake success on API failure", async () => {
    vi.spyOn(api, "deleteDocumentRequest").mockRejectedValue(
      new api.ApiError(503, "Storage cleanup failed"),
    );

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <AuthedActions />
      </AuthProvider>,
    );

    await screen.findByRole("button", { name: "Delete" });
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(api.deleteDocumentRequest).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirm delete/i }));
    await waitFor(() => {
      expect(screen.getByTestId("error")).toHaveTextContent(
        /storage cleanup failed/i,
      );
    });
    expect(screen.getByTestId("message")).toHaveTextContent("");
  });

  it("401 on download invalidates the session", async () => {
    vi.spyOn(api, "downloadDocumentRequest").mockRejectedValue(
      new api.ApiError(401, "Unauthorized"),
    );

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <AuthedActions />
      </AuthProvider>,
    );

    await screen.findByRole("button", { name: "Download" });
    await user.click(screen.getByRole("button", { name: "Download" }));

    await waitFor(() => {
      expect(screen.getByTestId("auth")).toHaveTextContent("unauthenticated");
    });
  });
});
