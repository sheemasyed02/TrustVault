import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentTable } from "@/components/document-table";
import type { DocumentListItem, UserPublic } from "@/lib/api";

const viewer: UserPublic = {
  id: "99999999-9999-9999-9999-999999999999",
  name: "Viewer",
  email: "viewer@example.com",
  role: "VIEWER",
  is_active: true,
  created_at: "2026-10-21T12:00:00+00:00",
  updated_at: "2026-10-21T12:00:00+00:00",
};

const sharedDocs: DocumentListItem[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    title: "Read Doc",
    category: "Legal",
    owner: {
      id: "00000000-0000-0000-0000-000000000001",
      name: "Owner",
      email: "owner@example.com",
    },
    mime_type:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    file_size: 10,
    created_at: "2026-10-21T12:00:00+00:00",
    your_access: "READ",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    title: "Edit Doc",
    category: "HR",
    owner: {
      id: "00000000-0000-0000-0000-000000000001",
      name: "Owner",
      email: "owner@example.com",
    },
    mime_type:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    file_size: 20,
    created_at: "2026-10-21T12:00:00+00:00",
    your_access: "EDIT",
  },
];

describe("DocumentTable shared mode", () => {
  it("shows READ and EDIT access badges and never delete for recipients", () => {
    render(
      <DocumentTable
        documents={sharedDocs}
        currentUser={viewer}
        mode="shared"
        onDownload={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText("View only")).toBeInTheDocument();
    expect(screen.getByText("Can edit")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
    expect(screen.getAllByRole("button", { name: /^PDF$/i })).toHaveLength(2);
  });
});
