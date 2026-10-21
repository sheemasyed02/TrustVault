import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiConfigError,
  ApiError,
  GENERIC_LOGIN_ERROR,
  getApiBaseUrl,
  getCurrentUserRequest,
  loginRequest,
} from "@/lib/api";

describe("getApiBaseUrl", () => {
  afterEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
  });

  it("normalizes trailing slashes", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000/";
    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("fails when missing", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    expect(() => getApiBaseUrl()).toThrow(ApiConfigError);
  });

  it("fails when invalid", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "not-a-url";
    expect(() => getApiBaseUrl()).toThrow(ApiConfigError);
  });
});

describe("loginRequest", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends JSON credentials to POST /auth/login", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "test-token",
          token_type: "bearer",
          expires_at: "2026-10-21T12:00:00+00:00",
          expires_in: 1800,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const result = await loginRequest("User@Example.com", "secret");
    expect(result.access_token).toBe("test-token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://127.0.0.1:8000/auth/login");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({
      "Content-Type": "application/json",
    });
    expect(JSON.parse(String(init?.body))).toEqual({
      email: "User@Example.com",
      password: "secret",
    });
    expect(JSON.stringify(init?.headers)).not.toContain("test-token");
  });

  it("maps invalid login to a safe ApiError", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: GENERIC_LOGIN_ERROR }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(loginRequest("a@b.com", "wrong")).rejects.toMatchObject({
      status: 401,
      detail: GENERIC_LOGIN_ERROR,
    } satisfies Partial<ApiError>);
  });

  it("surfaces network failures without fake success", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(loginRequest("a@b.com", "x")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("list and auth error handling", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces list errors without returning fake documents", async () => {
    const { listDocumentsRequest, ApiError } = await import("@/lib/api");
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(listDocumentsRequest("bad")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("getCurrentUserRequest", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends Authorization Bearer token to /users/me", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "00000000-0000-0000-0000-000000000001",
          name: "Owner",
          email: "owner@example.com",
          role: "OWNER",
          is_active: true,
          created_at: "2026-10-21T12:00:00+00:00",
          updated_at: "2026-10-21T12:00:00+00:00",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const user = await getCurrentUserRequest("jwt-value");
    expect(user.role).toBe("OWNER");
    const [, init] = fetchMock.mock.calls[0]!;
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer jwt-value",
    );
  });
});
