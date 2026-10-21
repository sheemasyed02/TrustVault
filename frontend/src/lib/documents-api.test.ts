import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listDocumentsRequest } from "@/lib/api";

describe("listDocumentsRequest", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls GET /documents with supported query params and bearer token", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          results: [],
          page: 1,
          page_size: 20,
          total: 0,
          total_pages: 0,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await listDocumentsRequest("tok", {
      title: "report",
      owner_id: "00000000-0000-0000-0000-000000000001",
      category: "Finance",
      page: 2,
      page_size: 20,
    });

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("http://127.0.0.1:8000/documents?");
    expect(String(url)).toContain("title=report");
    expect(String(url)).toContain("owner_id=00000000-0000-0000-0000-000000000001");
    expect(String(url)).toContain("category=Finance");
    expect(String(url)).toContain("page=2");
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok",
    );
  });

  it("does not treat hardcoded sample documents as API data", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          results: [
            {
              id: "11111111-1111-1111-1111-111111111111",
              title: "From API",
              category: "Legal",
              owner: {
                id: "00000000-0000-0000-0000-000000000001",
                name: "Owner",
                email: "owner@example.com",
              },
              mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              file_size: 10,
              created_at: "2026-10-21T12:00:00+00:00",
              your_access: "READ",
            },
          ],
          page: 1,
          page_size: 20,
          total: 1,
          total_pages: 1,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const data = await listDocumentsRequest("tok", { shared_only: true });
    expect(data.results).toHaveLength(1);
    expect(data.results[0]?.title).toBe("From API");
    expect(data.results[0]?.your_access).toBe("READ");
    expect(data.total).toBe(1);
    expect(String(vi.mocked(fetch).mock.calls[0]![0])).toContain("shared_only=true");
  });
});
