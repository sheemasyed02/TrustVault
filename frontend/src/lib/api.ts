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

export interface DocumentOwnerSummary {
  id: string;
  name: string;
  email: string;
}

export interface DocumentListItem {
  id: string;
  title: string;
  category: string;
  owner: DocumentOwnerSummary;
  mime_type: string;
  file_size: number;
  created_at: string;
}

export interface DocumentListResponse {
  results: DocumentListItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface DocumentDetail {
  id: string;
  title: string;
  category: string;
  description: string | null;
  owner: DocumentOwnerSummary;
  mime_type: string;
  file_size: number;
  sha256_checksum: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentDeleteResponse {
  id: string;
  deleted_at: string;
  storage_cleanup: string;
}

/** Query params supported by GET /documents (server-side authorization). */
export interface DocumentListParams {
  title?: string;
  owner_id?: string;
  owner_email?: string;
  category?: string;
  created_from?: string;
  created_to?: string;
  page?: number;
  page_size?: number;
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

function buildQuery(params: Record<string, string | number | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    qs.set(key, String(value));
  }
  const text = qs.toString();
  return text ? `?${text}` : "";
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

export async function listDocumentsRequest(
  token: string,
  params: DocumentListParams = {},
  signal?: AbortSignal,
): Promise<DocumentListResponse> {
  const query = buildQuery({
    title: params.title,
    owner_id: params.owner_id,
    owner_email: params.owner_email,
    category: params.category,
    created_from: params.created_from,
    created_to: params.created_to,
    page: params.page,
    page_size: params.page_size,
  });
  return apiRequest<DocumentListResponse>(`/documents${query}`, {
    method: "GET",
    token,
    signal,
  });
}

export async function getDocumentRequest(
  token: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${documentId}`, {
    method: "GET",
    token,
    signal,
  });
}

export async function deleteDocumentRequest(
  token: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentDeleteResponse> {
  return apiRequest<DocumentDeleteResponse>(`/documents/${documentId}`, {
    method: "DELETE",
    token,
    signal,
  });
}

export interface DownloadResult {
  blob: Blob;
  filename: string | null;
  contentType: string | null;
}

/** Authorized download — streams through the API (no public R2 URL). */
export async function downloadDocumentRequest(
  token: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<DownloadResult> {
  const base = getApiBaseUrl();
  let response: Response;
  try {
    response = await fetch(joinUrl(base, `/documents/${documentId}/download`), {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "*/*",
      },
      signal,
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

  const disposition = response.headers.get("content-disposition");
  let filename: string | null = null;
  if (disposition) {
    const match = /filename="([^"]+)"/i.exec(disposition);
    if (match?.[1]) filename = match[1];
  }

  const blob = await response.blob();
  return {
    blob,
    filename,
    contentType: response.headers.get("content-type"),
  };
}

/** Generic login failure copy — matches backend non-enumeration policy. */
export const GENERIC_LOGIN_ERROR = "Invalid email or password";
