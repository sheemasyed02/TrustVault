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

/** Effective document access for the authenticated caller (from PostgreSQL). */
export type DocumentAccessLevel = "OWNER" | "EDIT" | "READ";

export interface DocumentListItem {
  id: string;
  title: string;
  category: string;
  owner: DocumentOwnerSummary;
  original_filename?: string | null;
  mime_type: string;
  file_size: number;
  created_at: string;
  /** Document-level access from PostgreSQL (OWNER | EDIT | READ). */
  your_access: DocumentAccessLevel;
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
  /** When true, only documents shared with the caller (not owned). */
  shared_only?: boolean;
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

export interface RegisterResponse {
  id: string;
  name: string;
  email: string;
  role: string;
  message: string;
}

export async function registerRequest(
  body: { name: string; email: string; password: string },
  signal?: AbortSignal,
): Promise<RegisterResponse> {
  return apiRequest<RegisterResponse>("/auth/register", {
    method: "POST",
    body,
    signal,
  });
}

export interface ForgotPasswordResponse {
  message: string;
}

export async function forgotPasswordRequest(
  email: string,
  signal?: AbortSignal,
): Promise<ForgotPasswordResponse> {
  return apiRequest<ForgotPasswordResponse>("/auth/forgot-password", {
    method: "POST",
    body: { email },
    signal,
  });
}

export interface ResetPasswordResponse {
  message: string;
}

export async function resetPasswordRequest(
  body: {
    token: string;
    new_password: string;
    confirm_password: string;
  },
  signal?: AbortSignal,
): Promise<ResetPasswordResponse> {
  return apiRequest<ResetPasswordResponse>("/auth/reset-password", {
    method: "POST",
    body,
    signal,
  });
}

export interface PromotionRequestItem {
  id: string;
  requester_id: string;
  status: string;
  justification: string | null;
  admin_note: string | null;
  reviewed_by: string | null;
  created_at: string;
  reviewed_at: string | null;
  requester?: {
    id: string;
    name: string;
    email: string;
    role: string;
  } | null;
}

export interface PromotionListResponse {
  results: PromotionRequestItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export async function submitPromotionRequest(
  token: string,
  justification?: string,
  signal?: AbortSignal,
): Promise<PromotionRequestItem> {
  return apiRequest<PromotionRequestItem>("/promotions/requests", {
    method: "POST",
    token,
    body: { justification: justification || null },
    signal,
  });
}

export async function listMyPromotionRequests(
  token: string,
  signal?: AbortSignal,
): Promise<PromotionRequestItem[]> {
  return apiRequest<PromotionRequestItem[]>("/promotions/requests/me", {
    token,
    signal,
  });
}

export async function listAdminPromotionsRequest(
  token: string,
  params: { status?: string; page?: number; page_size?: number } = {},
  signal?: AbortSignal,
): Promise<PromotionListResponse> {
  const query = buildQuery({
    status: params.status,
    page: params.page,
    page_size: params.page_size,
  });
  return apiRequest<PromotionListResponse>(`/admin/promotions${query}`, {
    token,
    signal,
  });
}

export async function reviewPromotionRequest(
  token: string,
  requestId: string,
  body: { decision: "APPROVED" | "REJECTED"; admin_note?: string },
  signal?: AbortSignal,
): Promise<PromotionRequestItem> {
  return apiRequest<PromotionRequestItem>(
    `/admin/promotions/${requestId}/review`,
    {
      method: "POST",
      token,
      body,
      signal,
    },
  );
}

/** Ordinary Manage Users role assignment — OWNER or VIEWER only (never ADMIN). */
export async function patchAdminUserRoleRequest(
  token: string,
  userId: string,
  role: "OWNER" | "VIEWER",
  signal?: AbortSignal,
): Promise<AdminUserSummary> {
  return apiRequest<AdminUserSummary>(`/admin/users/${userId}/role`, {
    method: "PATCH",
    token,
    body: { role },
    signal,
  });
}

export async function listDocumentAuditRequest(
  token: string,
  documentId: string,
  params: {
    page?: number;
    page_size?: number;
    action?: string;
    focus?:
      | "external_views"
      | "owner_views"
      | "downloads"
      | "denied"
      | "all";
  } = {},
  signal?: AbortSignal,
): Promise<AuditEventListResponse> {
  const query = buildQuery({
    page: params.page,
    page_size: params.page_size,
    action: params.action,
    focus: params.focus,
  });
  return apiRequest<AuditEventListResponse>(
    `/documents/${documentId}/audit${query}`,
    { token, signal },
  );
}

export interface DocumentViewActivityItem {
  document_id: string;
  title: string;
  owner_id: string;
  owner_name: string;
  owner_email: string;
  total_views: number;
  distinct_viewers: number;
  latest_view_at: string | null;
}

export interface DocumentViewPlatformSummary {
  total_view_events: number;
  documents_with_views: number;
  most_viewed: DocumentViewActivityItem[];
}

export interface DocumentViewActivityListResponse {
  results: DocumentViewActivityItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  summary?: DocumentViewPlatformSummary | null;
}

export async function listOwnerDocumentViewActivityRequest(
  token: string,
  params: { page?: number; page_size?: number } = {},
  signal?: AbortSignal,
): Promise<DocumentViewActivityListResponse> {
  const query = buildQuery({
    page: params.page,
    page_size: params.page_size,
  });
  return apiRequest<DocumentViewActivityListResponse>(
    `/documents/view-activity${query}`,
    { token, signal },
  );
}

export async function listAdminDocumentViewsRequest(
  token: string,
  params: {
    page?: number;
    page_size?: number;
    q?: string;
    owner_id?: string;
    viewer_id?: string;
    created_from?: string;
    created_to?: string;
  } = {},
  signal?: AbortSignal,
): Promise<DocumentViewActivityListResponse> {
  const query = buildQuery({
    page: params.page,
    page_size: params.page_size,
    q: params.q,
    owner_id: params.owner_id,
    viewer_id: params.viewer_id,
    created_from: params.created_from,
    created_to: params.created_to,
  });
  return apiRequest<DocumentViewActivityListResponse>(
    `/admin/audit/document-views${query}`,
    { token, signal },
  );
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

export async function updateCurrentUserProfileRequest(
  token: string,
  body: { name: string },
  signal?: AbortSignal,
): Promise<UserPublic> {
  return apiRequest<UserPublic>("/users/me", {
    method: "PATCH",
    token,
    body,
    signal,
  });
}

export async function changePasswordRequest(
  token: string,
  body: {
    current_password: string;
    new_password: string;
    confirm_password: string;
  },
  signal?: AbortSignal,
): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/users/me/password", {
    method: "POST",
    token,
    body,
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
    shared_only: params.shared_only === true ? "true" : undefined,
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

/* —— Administrator APIs (ADMIN role required server-side) —— */

export interface AdminUserSummary {
  id: string;
  name: string;
  email: string;
  role: UserRole | string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  account_status?: string;
  promotion_request_status?: string | null;
  promotion_requested_at?: string | null;
  pending_promotion_id?: string | null;
}

export interface AdminPromotionSummary {
  id: string;
  status: string;
  justification: string | null;
  admin_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export interface AdminUserActivitySummary {
  owned_documents: number;
  active_grants_received: number;
  audit_events_as_actor: number;
  denied_audit_events_as_actor: number;
}

export interface AdminUserProfile extends AdminUserSummary {
  latest_promotion: AdminPromotionSummary | null;
  activity: AdminUserActivitySummary;
}

export interface AdminUserListResponse {
  results: AdminUserSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminUserListParams {
  page?: number;
  page_size?: number;
  q?: string;
  role?: UserRole | "";
  is_active?: boolean | "";
  promotion_status?: "PENDING" | "APPROVED" | "REJECTED" | "NONE" | "";
}

export interface AdminSummaryResponse {
  users_total: number;
  users_active: number;
  users_inactive: number;
  audit_success_total: number;
  audit_denied_total: number;
}

export interface AuditEventItem {
  id: string;
  created_at: string;
  actor_id: string | null;
  actor_name?: string | null;
  actor_email?: string | null;
  action: string;
  document_id: string | null;
  document_title?: string | null;
  document_owner_id?: string | null;
  document_owner_name?: string | null;
  document_owner_email?: string | null;
  is_owner_self_view?: boolean;
  target_user_id: string | null;
  target_user_name?: string | null;
  target_user_email?: string | null;
  outcome: "SUCCESS" | "DENIED" | string;
  reason_code: string | null;
  request_id: string | null;
  metadata: Record<string, unknown>;
  previous_hash: string | null;
  event_hash: string;
}

export interface DocumentAuditSummary {
  successful_views: number;
  distinct_viewers?: number;
  latest_view_at?: string | null;
  external_views?: number;
  distinct_external_viewers?: number;
  latest_external_view_at?: string | null;
  owner_self_views?: number;
  successful_downloads: number;
  denied_access_attempts: number;
  permission_grants: number;
  permission_revocations: number;
  content_updates: number;
  metadata_updates: number;
  uploads: number;
  deletions: number;
}

export interface AuditEventListResponse {
  results: AuditEventItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  summary?: DocumentAuditSummary | null;
}

export interface AuditListParams {
  page?: number;
  page_size?: number;
  actor_id?: string;
  action?: string;
  document_id?: string;
  owner_id?: string;
  outcome?: "SUCCESS" | "DENIED" | "";
  created_from?: string;
  created_to?: string;
}

export interface AuditIntegrityResult {
  valid: boolean;
  event_count: number;
  checked_count: number;
  first_failure_index: number | null;
  first_failure_event_id: string | null;
  reason_code: string | null;
  detail: string;
}

export async function getAdminSummaryRequest(
  token: string,
  signal?: AbortSignal,
): Promise<AdminSummaryResponse> {
  return apiRequest<AdminSummaryResponse>("/admin/summary", { token, signal });
}

export async function listAdminUsersRequest(
  token: string,
  params: AdminUserListParams = {},
  signal?: AbortSignal,
): Promise<AdminUserListResponse> {
  const query = buildQuery({
    page: params.page,
    page_size: params.page_size,
    q: params.q,
    role: params.role || undefined,
    is_active:
      params.is_active === "" || params.is_active === undefined
        ? undefined
        : params.is_active
          ? "true"
          : "false",
    promotion_status: params.promotion_status || undefined,
  });
  return apiRequest<AdminUserListResponse>(`/admin/users${query}`, {
    token,
    signal,
  });
}

export async function getAdminUserProfileRequest(
  token: string,
  userId: string,
  signal?: AbortSignal,
): Promise<AdminUserProfile> {
  return apiRequest<AdminUserProfile>(`/admin/users/${userId}`, {
    token,
    signal,
  });
}

export async function patchAdminUserStatusRequest(
  token: string,
  userId: string,
  isActive: boolean,
  signal?: AbortSignal,
): Promise<AdminUserSummary> {
  return apiRequest<AdminUserSummary>(`/admin/users/${userId}`, {
    method: "PATCH",
    token,
    body: { is_active: isActive },
    signal,
  });
}

export async function listAuditEventsRequest(
  token: string,
  params: AuditListParams = {},
  signal?: AbortSignal,
): Promise<AuditEventListResponse> {
  const query = buildQuery({
    page: params.page,
    page_size: params.page_size,
    actor_id: params.actor_id,
    action: params.action,
    document_id: params.document_id,
    owner_id: params.owner_id,
    outcome: params.outcome || undefined,
    created_from: params.created_from,
    created_to: params.created_to,
  });
  return apiRequest<AuditEventListResponse>(`/admin/audit/events${query}`, {
    token,
    signal,
  });
}

export async function verifyAuditIntegrityRequest(
  token: string,
  signal?: AbortSignal,
): Promise<AuditIntegrityResult> {
  return apiRequest<AuditIntegrityResult>("/admin/audit/integrity", {
    token,
    signal,
  });
}
