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
  original_filename?: string | null;
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

/** Effective document access for the authenticated caller (from PostgreSQL). */
export type DocumentAccessLevel = "OWNER" | "EDIT" | "READ";

export interface DocumentDetail {
  id: string;
  title: string;
  category: string;
  description: string | null;
  owner: DocumentOwnerSummary;
  original_filename?: string | null;
  mime_type: string;
  file_size: number;
  sha256_checksum: string;
  created_at: string;
  updated_at: string;
  your_access: DocumentAccessLevel;
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

/** Minimal share-recipient fields from GET /users/search. */
export interface UserSearchHit {
  id: string;
  name: string;
  email: string;
}

export interface UserSearchResponse {
  results: UserSearchHit[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface UserSearchParams {
  q: string;
  page?: number;
  page_size?: number;
  /** Omit these user ids (e.g. document owner) from results. */
  exclude_user_id?: string | string[];
}

/** Authenticated directory search — never hardcode demo users in the UI. */
export async function searchUsersRequest(
  token: string,
  params: UserSearchParams,
  signal?: AbortSignal,
): Promise<UserSearchResponse> {
  const exclude = Array.isArray(params.exclude_user_id)
    ? params.exclude_user_id.filter(Boolean).join(",")
    : params.exclude_user_id;
  const query = buildQuery({
    q: params.q,
    page: params.page,
    page_size: params.page_size,
    exclude_user_id: exclude || undefined,
  });
  return apiRequest<UserSearchResponse>(`/users/search${query}`, {
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

export interface DocumentMetadataPatch {
  title?: string;
  category?: string;
  description?: string | null;
}

export async function patchDocumentRequest(
  token: string,
  documentId: string,
  body: DocumentMetadataPatch,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${documentId}`, {
    method: "PATCH",
    token,
    body,
    signal,
  });
}

export interface DocumentContentPatch {
  text: string;
}

/** Replace DOCX body text — owner or EDIT grantee only. */
export async function putDocumentContentRequest(
  token: string,
  documentId: string,
  body: DocumentContentPatch,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${documentId}/content`, {
    method: "PUT",
    token,
    body,
    signal,
  });
}

export type DocumentPermissionLevel = "READ" | "EDIT";

export interface PermissionUserSummary {
  id: string;
  name: string;
  email: string;
}

export interface PermissionGrant {
  id: string;
  document_id: string;
  user: PermissionUserSummary;
  permission: DocumentPermissionLevel | string;
  granted_at: string;
  granted_by: PermissionUserSummary;
  regranted: boolean;
}

export interface PermissionListResponse {
  document_id: string;
  permissions: PermissionGrant[];
}

export interface PermissionRevokeResponse {
  document_id: string;
  user_id: string;
  permission: string;
  revoked_at: string;
}

export async function listDocumentPermissionsRequest(
  token: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<PermissionListResponse> {
  return apiRequest<PermissionListResponse>(
    `/documents/${documentId}/permissions`,
    { method: "GET", token, signal },
  );
}

export async function grantDocumentPermissionRequest(
  token: string,
  documentId: string,
  body: { user_id: string; permission: DocumentPermissionLevel },
  signal?: AbortSignal,
): Promise<PermissionGrant> {
  return apiRequest<PermissionGrant>(`/documents/${documentId}/permissions`, {
    method: "POST",
    token,
    body,
    signal,
  });
}

export async function revokeDocumentPermissionRequest(
  token: string,
  documentId: string,
  userId: string,
  signal?: AbortSignal,
): Promise<PermissionRevokeResponse> {
  return apiRequest<PermissionRevokeResponse>(
    `/documents/${documentId}/permissions/${userId}`,
    { method: "DELETE", token, signal },
  );
}

export interface UploadDocumentFields {
  title: string;
  category: string;
  description?: string;
  file: File;
}

/**
 * Multipart upload. Do not set Content-Type manually — the browser must
 * supply the multipart boundary.
 */
export async function uploadDocumentRequest(
  token: string,
  fields: UploadDocumentFields,
  signal?: AbortSignal,
): Promise<DocumentDetail> {
  const base = getApiBaseUrl();
  const form = new FormData();
  form.append("title", fields.title);
  form.append("category", fields.category);
  if (fields.description !== undefined && fields.description !== "") {
    form.append("description", fields.description);
  }
  form.append("file", fields.file);

  let response: Response;
  try {
    response = await fetch(joinUrl(base, "/documents"), {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: form,
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

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiError(
      response.status,
      "Unexpected non-JSON response from the TrustVault API.",
    );
  }

  return (await response.json()) as DocumentDetail;
}

export interface DownloadResult {
  blob: Blob;
  filename: string | null;
  contentType: string | null;
}

const MIME_EXTENSIONS: Record<string, string> = {
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
    ".docx",
  // Legacy types may still exist for older uploads.
  "application/pdf": ".pdf",
  "image/png": ".png",
  "image/jpeg": ".jpg",
};

/** Prefer Content-Disposition; never invent a misleading .bin for known types. */
export function resolveDownloadFilename(options: {
  headerFilename: string | null;
  fallbackTitle?: string | null;
  originalFilename?: string | null;
  contentType?: string | null;
}): string {
  if (options.headerFilename?.trim()) return options.headerFilename.trim();
  const raw =
    options.originalFilename?.trim() ||
    options.fallbackTitle?.trim() ||
    "document";
  const base = raw.replace(/[\\/]+/g, "_").slice(0, 200) || "document";
  const mime = (options.contentType ?? "").split(";")[0]?.trim().toLowerCase();
  const ext = mime ? MIME_EXTENSIONS[mime] : undefined;
  if (ext && !base.toLowerCase().endsWith(ext)) return `${base}${ext}`;
  return base;
}

function parseContentDispositionFilename(
  disposition: string | null,
): string | null {
  if (!disposition) return null;
  const utf8 = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(disposition);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].trim().replace(/^"+|"+$/g, ""));
    } catch {
      // Fall through to basic filename=.
    }
  }
  const basic = /filename\s*=\s*"([^"]+)"/i.exec(disposition);
  if (basic?.[1]) return basic[1];
  const unquoted = /filename\s*=\s*([^;]+)/i.exec(disposition);
  if (unquoted?.[1]) return unquoted[1].trim().replace(/^"+|"+$/g, "");
  return null;
}

export interface FetchDocumentContentOptions {
  signal?: AbortSignal;
  /** inline = content preview; attachment = save to disk (default). */
  disposition?: "attachment" | "inline";
}

/**
 * Authorized binary fetch through the API (no public R2 URL).
 * Reads the body as ArrayBuffer so bytes are never decoded as text/JSON.
 * Error responses raise ApiError and are never returned as a Blob to save.
 */
export async function fetchDocumentContentRequest(
  token: string,
  documentId: string,
  options: FetchDocumentContentOptions = {},
): Promise<DownloadResult> {
  const base = getApiBaseUrl();
  const disposition = options.disposition ?? "attachment";
  const path = `/documents/${documentId}/download?disposition=${disposition}`;
  let response: Response;
  try {
    response = await fetch(joinUrl(base, path), {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "*/*",
      },
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

  const contentTypeHeader = response.headers.get("content-type");
  const contentType = contentTypeHeader
    ? contentTypeHeader.split(";")[0]!.trim()
    : null;
  // Reject accidental JSON/HTML success bodies pretending to be files.
  if (
    contentType &&
    (contentType.includes("application/json") ||
      contentType.includes("text/html"))
  ) {
    throw new ApiError(
      response.status,
      "Unexpected non-file response from the TrustVault API.",
    );
  }

  const buffer = await response.arrayBuffer();
  const blob = new Blob([buffer], {
    type: contentType || "application/octet-stream",
  });

  return {
    blob,
    filename: parseContentDispositionFilename(
      response.headers.get("content-disposition"),
    ),
    contentType,
  };
}

/** Authorized download — streams through the API (no public R2 URL). */
export async function downloadDocumentRequest(
  token: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<DownloadResult> {
  return fetchDocumentContentRequest(token, documentId, {
    signal,
    disposition: "attachment",
  });
}

/** Authorized inline content fetch (same bytes as download). */
export async function previewDocumentRequest(
  token: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<DownloadResult> {
  return fetchDocumentContentRequest(token, documentId, {
    signal,
    disposition: "inline",
  });
}

/** Generic login failure copy — matches backend non-enumeration policy. */
export const GENERIC_LOGIN_ERROR = "Invalid email or password";
