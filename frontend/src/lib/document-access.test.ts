import { describe, expect, it } from "vitest";

import {
  formatDocumentAccessLabel,
  getDocumentUiAccess,
} from "@/lib/document-access";
import type { DocumentDetail, UserPublic } from "@/lib/api";

const owner: UserPublic = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "Owner",
  email: "owner@example.com",
  role: "OWNER",
  is_active: true,
  created_at: "2026-10-21T12:00:00+00:00",
  updated_at: "2026-10-21T12:00:00+00:00",
};

const baseDoc = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Q3",
  category: "Finance",
  description: null,
  owner: { id: owner.id, name: owner.name, email: owner.email },
  mime_type:
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  file_size: 1,
  sha256_checksum: "x",
  created_at: "2026-10-21T12:00:00+00:00",
  updated_at: "2026-10-21T12:00:00+00:00",
} as const;

describe("formatDocumentAccessLabel", () => {
  it("distinguishes document access from platform roles", () => {
    expect(formatDocumentAccessLabel("OWNER")).toBe("Document owner");
    expect(formatDocumentAccessLabel("EDIT")).toBe("EDIT grant");
    expect(formatDocumentAccessLabel("READ")).toBe("READ grant");
  });
});

describe("getDocumentUiAccess", () => {
  it("gives owner full content/metadata/share/delete", () => {
    const doc: DocumentDetail = { ...baseDoc, your_access: "OWNER" };
    const access = getDocumentUiAccess(owner, doc);
    expect(access.isOwner).toBe(true);
    expect(access.canEditContent).toBe(true);
    expect(access.canEditMetadata).toBe(true);
    expect(access.canManageSharing).toBe(true);
    expect(access.canDelete).toBe(true);
  });

  it("gives EDIT grantee content edit but not metadata/share/delete", () => {
    const viewer: UserPublic = {
      ...owner,
      id: "99999999-9999-9999-9999-999999999999",
      role: "VIEWER",
      email: "viewer@example.com",
    };
    const doc: DocumentDetail = { ...baseDoc, your_access: "EDIT" };
    const access = getDocumentUiAccess(viewer, doc);
    expect(access.isOwner).toBe(false);
    expect(access.canEditContent).toBe(true);
    expect(access.canEditMetadata).toBe(false);
    expect(access.canManageSharing).toBe(false);
    expect(access.canDelete).toBe(false);
  });

  it("gives READ grantee view-only UI", () => {
    const viewer: UserPublic = {
      ...owner,
      id: "99999999-9999-9999-9999-999999999999",
      role: "VIEWER",
      email: "viewer@example.com",
    };
    const doc: DocumentDetail = { ...baseDoc, your_access: "READ" };
    const access = getDocumentUiAccess(viewer, doc);
    expect(access.canEditContent).toBe(false);
    expect(access.canEditMetadata).toBe(false);
    expect(access.canManageSharing).toBe(false);
    expect(access.canDelete).toBe(false);
  });

  it("does not treat platform OWNER role as document ownership without your_access", () => {
    const platformOwner: UserPublic = {
      ...owner,
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      role: "OWNER",
    };
    const doc: DocumentDetail = {
      ...baseDoc,
      your_access: "READ",
      owner: {
        id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        name: "Other",
        email: "other@example.com",
      },
    };
    const access = getDocumentUiAccess(platformOwner, doc);
    expect(access.isOwner).toBe(false);
    expect(access.canManageSharing).toBe(false);
    expect(access.canDelete).toBe(false);
    expect(access.canEditContent).toBe(false);
    expect(access.canEditMetadata).toBe(false);
  });
});
