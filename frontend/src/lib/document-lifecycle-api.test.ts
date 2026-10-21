import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  downloadDocumentRequest,
  grantDocumentPermissionRequest,
  patchDocumentRequest,
  putDocumentContentRequest,
  resolveDownloadFilename,
  searchUsersRequest,
  uploadDocumentRequest,
  ApiError,
} from "@/lib/api";

describe("document lifecycle API client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uploadDocumentRequest sends multipart FormData without a manual Content-Type", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "11111111-1111-1111-1111-111111111111",
          title: "Report",
          category: "Finance",
          description: null,
          owner: {
            id: "00000000-0000-0000-0000-000000000001",
            name: "Owner",
            email: "owner@example.com",
          },
          mime_type:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          file_size: 12,
          sha256_checksum: "abc",
          created_at: "2026-10-21T12:00:00+00:00",
          updated_at: "2026-10-21T12:00:00+00:00",
          your_access: "OWNER",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    const file = new File(["PK"], "report.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    await uploadDocumentRequest("tok", {
      title: "Report",
      category: "Finance",
      file,
    });

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("http://127.0.0.1:8000/documents");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeInstanceOf(FormData);
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok");
    expect(headers["Content-Type"]).toBeUndefined();
    const form = init?.body as FormData;
    expect(form.get("title")).toBe("Report");
    expect(form.get("category")).toBe("Finance");
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("uploadDocumentRequest surfaces failures without returning success data", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "File exceeds the 10 MiB size limit" }), {
        status: 413,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const file = new File(["x"], "big.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    await expect(
      uploadDocumentRequest("tok", {
        title: "Big",
        category: "HR",
        file,
      }),
    ).rejects.toMatchObject({
      status: 413,
      detail: "File exceeds the 10 MiB size limit",
    });
  });

  it("downloadDocumentRequest uses the authenticated backend download path", async () => {
    const docxBytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04]); // PK..
    const docxType =
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    vi.mocked(fetch).mockResolvedValue(
      new Response(docxBytes, {
        status: 200,
        headers: {
          "Content-Type": docxType,
          "Content-Disposition": 'attachment; filename="safe.docx"',
        },
      }),
    );

    const result = await downloadDocumentRequest(
      "tok",
      "11111111-1111-1111-1111-111111111111",
    );
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toContain(
      "/documents/11111111-1111-1111-1111-111111111111/download",
    );
    expect(String(url)).toContain("disposition=attachment");
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok",
    );
    expect(result.filename).toBe("safe.docx");
    expect(result.contentType).toBe(docxType);
    expect(result.blob.type).toBe(docxType);
    expect(result.blob.size).toBe(docxBytes.byteLength);
  });

  it("resolveDownloadFilename never falls back to .bin for DOCX", () => {
    const docxType =
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    expect(
      resolveDownloadFilename({
        headerFilename: null,
        fallbackTitle: "My Report",
        contentType: docxType,
      }),
    ).toBe("My Report.docx");
    expect(
      resolveDownloadFilename({
        headerFilename: "from-header.docx",
        fallbackTitle: "ignored",
        contentType: docxType,
      }),
    ).toBe("from-header.docx");
  });

  it("failed download does not return a blob to save", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Document not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(
      downloadDocumentRequest("tok", "11111111-1111-1111-1111-111111111111"),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("rejects JSON success bodies so error pages are not saved as files", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "oops" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(
      downloadDocumentRequest("tok", "11111111-1111-1111-1111-111111111111"),
    ).rejects.toMatchObject({
      detail: "Unexpected non-file response from the TrustVault API.",
    });
  });

  it("patchDocumentRequest sends only permitted metadata fields", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "11111111-1111-1111-1111-111111111111",
          title: "New",
          category: "Legal",
          description: "notes",
          owner: {
            id: "00000000-0000-0000-0000-000000000001",
            name: "Owner",
            email: "owner@example.com",
          },
          mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          file_size: 12,
          sha256_checksum: "abc",
          created_at: "2026-10-21T12:00:00+00:00",
          updated_at: "2026-10-21T13:00:00+00:00",
          your_access: "OWNER",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await patchDocumentRequest("tok", "11111111-1111-1111-1111-111111111111", {
      title: "New",
      category: "Legal",
      description: "notes",
    });

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({
      title: "New",
      category: "Legal",
      description: "notes",
    });
  });

  it("putDocumentContentRequest PUTs text to /documents/{id}/content", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "11111111-1111-1111-1111-111111111111",
          title: "Report",
          category: "Finance",
          description: null,
          owner: {
            id: "00000000-0000-0000-0000-000000000001",
            name: "Owner",
            email: "owner@example.com",
          },
          mime_type:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          file_size: 40,
          sha256_checksum: "def",
          created_at: "2026-10-21T12:00:00+00:00",
          updated_at: "2026-10-21T14:00:00+00:00",
          your_access: "EDIT",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await putDocumentContentRequest("tok", "11111111-1111-1111-1111-111111111111", {
      text: "Revised body",
    });

    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toContain("/documents/11111111-1111-1111-1111-111111111111/content");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ text: "Revised body" });
  });

  it("searchUsersRequest calls GET /users/search with q and auth", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          results: [
            {
              id: "33333333-3333-3333-3333-333333333333",
              name: "Bob Viewer",
              email: "bob@example.com",
            },
          ],
          page: 1,
          page_size: 10,
          total: 1,
          total_pages: 1,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await searchUsersRequest("tok", { q: "bob" });
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toContain("/users/search");
    expect(String(url)).toContain("q=bob");
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok",
    );
    expect(result.results[0]?.email).toBe("bob@example.com");
    expect(result.results[0]).not.toHaveProperty("password_hash");
  });

  it("grantDocumentPermissionRequest sends selected READ or EDIT", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "22222222-2222-2222-2222-222222222222",
          document_id: "11111111-1111-1111-1111-111111111111",
          user: {
            id: "33333333-3333-3333-3333-333333333333",
            name: "Viewer",
            email: "viewer@example.com",
          },
          permission: "EDIT",
          granted_at: "2026-10-21T12:00:00+00:00",
          granted_by: {
            id: "00000000-0000-0000-0000-000000000001",
            name: "Owner",
            email: "owner@example.com",
          },
          regranted: false,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    await grantDocumentPermissionRequest(
      "tok",
      "11111111-1111-1111-1111-111111111111",
      {
        user_id: "33333333-3333-3333-3333-333333333333",
        permission: "EDIT",
      },
    );

    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(String(url)).toContain("/permissions");
    expect(JSON.parse(String(init?.body))).toEqual({
      user_id: "33333333-3333-3333-3333-333333333333",
      permission: "EDIT",
    });
  });
});
