/**
 * Typed TrustVault API client for the FastAPI backend.
 * Tokens must never be logged. Credentials are never embedded here.
 */

export type UserRole = "ADMIN" | "OWNER" | "VIEWER";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  expires_in: number;
}

export interface UserPublic {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export class ApiConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigError";
  }
}

export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (raw === undefined || raw.trim() === "") {
    throw new ApiConfigError(
      "NEXT_PUBLIC_API_BASE_URL is missing. Set it in frontend/.env.local.",
    );
  }
  let base: string;
  try {
    base = new URL(raw.trim()).toString().replace(/\/+$/, "");
  } catch {
    throw new ApiConfigError(
      "NEXT_PUBLIC_API_BASE_URL is not a valid absolute URL.",
    );
  }
  if (!base.startsWith("http://") && !base.startsWith("https://")) {
    throw new ApiConfigError(
      "NEXT_PUBLIC_API_BASE_URL must use http or https.",
    );
  }
  return base;
}

function joinUrl(base: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

async function parseErrorDetail(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        return (body as { detail: string }).detail;
      }
    } catch {
      // Fall through to generic message.
    }
  }
  return `Request failed with status ${response.status}`;
}

export interface ApiRequestOptions {
  method?: string;
  body?: unknown;
  token?: string;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

/**
 * Call a TrustVault API path relative to NEXT_PUBLIC_API_BASE_URL.
 * Pass token only for authenticated TrustVault routes — never for third parties.
 */
export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const base = getApiBaseUrl();
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...options.headers,
  };

  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  let response: Response;
  try {
    response = await fetch(joinUrl(base, path), {
      method: options.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: options.signal,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      0,
      "Unable to reach the TrustVault API. Check that the backend is running.",
    );
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiError(
      response.status,
      "Unexpected non-JSON response from the TrustVault API.",
    );
  }

  return (await response.json()) as T;
}

export async function loginRequest(
  email: string,
  password: string,
  signal?: AbortSignal,
): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
    signal,
  });
}

export async function getCurrentUserRequest(
  token: string,
  signal?: AbortSignal,
): Promise<UserPublic> {
  return apiRequest<UserPublic>("/users/me", {
    method: "GET",
    token,
    signal,
  });
}

/** Generic login failure copy — matches backend non-enumeration policy. */
export const GENERIC_LOGIN_ERROR = "Invalid email or password";
