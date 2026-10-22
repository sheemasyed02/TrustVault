import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/auth-provider";
import { DocumentMetadataForm } from "@/components/document-metadata-form";
import { DocumentPermissionsPanel } from "@/components/document-permissions-panel";
import { UploadDocumentForm } from "@/components/upload-document-form";
import * as api from "@/lib/api";
import type { DocumentDetail, UserPublic } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() }),
}));

const owner: UserPublic = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Owner",
  email: "owner@example.com",
  role: "OWNER",
  is_active: true,
  created_at: "2026-10-21T12:00:00+00:00",
  updated_at: "2026-10-21T12:00:00+00:00",
};

const sampleDoc: DocumentDetail = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Q3",
  category: "Finance",
  description: "notes",
  owner: {
    id: owner.id,
    name: owner.name,
    email: owner.email,
  },
  mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  file_size: 100,
  sha256_checksum: "abc",
  created_at: "2026-10-21T12:00:00+00:00",
  updated_at: "2026-10-21T12:00:00+00:00",
  your_access: "OWNER",
};

function mockAuthedSession() {
  vi.spyOn(api, "loginRequest").mockResolvedValue({
    access_token: "tok",
    token_type: "bearer",
    expires_at: "2099-01-01T00:00:00+00:00",
    expires_in: 3600,
  });
  vi.spyOn(api, "getCurrentUserRequest").mockResolvedValue(owner);
}

function Authed({ children }: { children: ReactNode }) {
  const { login, status } = useAuth();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void login("owner@example.com", "password").then(() => setReady(true));
  }, [login]);
  if (!ready || status !== "authenticated") {
    return <p>booting</p>;
  }
  return children;
}

describe("document lifecycle UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockAuthedSession();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not show metadata editor when canEdit is false (READ UI)", () => {
    render(
      <AuthProvider>
        <DocumentMetadataForm
          document={sampleDoc}
          canEdit={false}
          onUpdated={() => undefined}
        />
      </AuthProvider>,
    );
    expect(screen.queryByLabelText(/^Title$/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /save changes/i })).toBeNull();
  });

  it("hides sharing panel entirely for non-owners", () => {
    const { container } = render(
      <AuthProvider>
        <DocumentPermissionsPanel documentId={sampleDoc.id} canManage={false} />
      </AuthProvider>,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("button", { name: /grant access/i })).toBeNull();
  });

  it("upload failure is not shown as success", async () => {
    const uploadSpy = vi
      .spyOn(api, "uploadDocumentRequest")
      .mockRejectedValue(new api.ApiError(415, "Unsupported file type"));

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <UploadDocumentForm />
        </Authed>
      </AuthProvider>,
    );

    await screen.findByRole("button", { name: /upload document/i });
    await user.type(screen.getByLabelText(/^Title$/i), "Report");
    await user.type(screen.getByLabelText(/^Category$/i), "Finance");
    const file = new File(["PK"], "a.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    await user.upload(screen.getByLabelText(/^File$/i), file);
    await user.click(screen.getByRole("button", { name: /upload document/i }));

    await waitFor(() => {
      expect(uploadSpy).toHaveBeenCalled();
    });
    expect(await screen.findByTestId("upload-error")).toHaveTextContent(
      /unsupported file type/i,
    );
    expect(screen.queryByText(/upload complete/i)).toBeNull();
  });

  it("owner can grant EDIT and must confirm before revoke refreshes the list", async () => {
    const listSpy = vi
      .spyOn(api, "listDocumentPermissionsRequest")
      .mockResolvedValue({
        document_id: sampleDoc.id,
        permissions: [
          {
            id: "22222222-2222-2222-2222-222222222222",
            document_id: sampleDoc.id,
            user: {
              id: "33333333-3333-3333-3333-333333333333",
              name: "Viewer",
              email: "viewer@example.com",
            },
            permission: "READ",
            granted_at: "2026-10-21T12:00:00+00:00",
            granted_by: {
              id: owner.id,
              name: owner.name,
              email: owner.email,
            },
            regranted: false,
          },
        ],
      });
    const grantSpy = vi
      .spyOn(api, "grantDocumentPermissionRequest")
      .mockResolvedValue({
        id: "44444444-4444-4444-4444-444444444444",
        document_id: sampleDoc.id,
        user: {
          id: "55555555-5555-5555-5555-555555555555",
          name: "Editor",
          email: "editor@example.com",
        },
        permission: "EDIT",
        granted_at: "2026-10-21T12:00:00+00:00",
        granted_by: {
          id: owner.id,
          name: owner.name,
          email: owner.email,
        },
        regranted: false,
      });
    const revokeSpy = vi
      .spyOn(api, "revokeDocumentPermissionRequest")
      .mockResolvedValue({
        document_id: sampleDoc.id,
        user_id: "33333333-3333-3333-3333-333333333333",
        permission: "READ",
        revoked_at: "2026-10-21T13:00:00+00:00",
      });

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <DocumentPermissionsPanel documentId={sampleDoc.id} canManage />
        </Authed>
      </AuthProvider>,
    );

    await screen.findByText(/viewer@example.com/i);
    expect(listSpy).toHaveBeenCalled();

    const recipientId = "55555555-5555-4555-a555-555555555555";
    const searchSpy = vi.spyOn(api, "searchUsersRequest").mockResolvedValue({
      results: [
        {
          id: recipientId,
          name: "Editor",
          email: "editor@example.com",
        },
      ],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    });

    await user.type(screen.getByLabelText(/find recipient/i), "editor");
    await waitFor(() => {
      expect(searchSpy).toHaveBeenCalled();
    });
    await user.click(await screen.findByRole("button", { name: /editor@example.com/i }));
    await user.selectOptions(screen.getByLabelText(/^Permission$/i), "EDIT");
    await user.click(screen.getByRole("button", { name: /grant access/i }));

    await waitFor(() => {
      expect(grantSpy).toHaveBeenCalledWith("tok", sampleDoc.id, {
        user_id: recipientId,
        permission: "EDIT",
      });
    });

    await user.click(screen.getByRole("button", { name: /^Revoke$/i }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(revokeSpy).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirm revoke/i }));
    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalled();
      expect(listSpy.mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("uses live user search instead of hardcoding demo accounts", async () => {
    vi.spyOn(api, "listDocumentPermissionsRequest").mockResolvedValue({
      document_id: sampleDoc.id,
      permissions: [],
    });
    const searchSpy = vi.spyOn(api, "searchUsersRequest").mockResolvedValue({
      results: [],
      page: 1,
      page_size: 10,
      total: 0,
      total_pages: 0,
    });

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <DocumentPermissionsPanel documentId={sampleDoc.id} canManage />
        </Authed>
      </AuthProvider>,
    );

    expect(
      screen.queryByText(/no user search\/list API yet/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/sheema@trustvault\.demo/i)).toBeNull();

    const searchInput = await screen.findByLabelText(/find recipient/i);
    await user.type(searchInput, "nobody");
    await waitFor(() => {
      expect(searchSpy).toHaveBeenCalled();
    });
    expect(await screen.findByText(/no matching active users/i)).toBeInTheDocument();
  });

  it("metadata form does not claim success before the API responds", async () => {
    let resolvePatch: (value: DocumentDetail) => void = () => undefined;
    const patchSpy = vi.spyOn(api, "patchDocumentRequest").mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePatch = resolve;
        }),
    );

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Authed>
          <DocumentMetadataForm
            document={sampleDoc}
            canEdit
            onUpdated={() => undefined}
          />
        </Authed>
      </AuthProvider>,
    );

    await screen.findByRole("button", { name: /save changes/i });
    await user.clear(screen.getByLabelText(/^Title$/i));
    await user.type(screen.getByLabelText(/^Title$/i), "Updated");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(patchSpy).toHaveBeenCalled();
    expect(screen.queryByText(/metadata updated/i)).toBeNull();

    resolvePatch({ ...sampleDoc, title: "Updated" });
    expect(await screen.findByText(/metadata updated/i)).toBeInTheDocument();
    expect(patchSpy.mock.calls[0]?.[2]).toEqual({
      title: "Updated",
      category: "Finance",
      description: "notes",
    });
  });
});
