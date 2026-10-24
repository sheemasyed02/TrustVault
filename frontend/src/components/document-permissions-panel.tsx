"use client";

import { LoaderCircle, Share2, Shield } from "lucide-react";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { UserSearchPicker } from "@/components/user-search-picker";
import {
  ApiError,
  grantDocumentPermissionRequest,
  listDocumentPermissionsRequest,
  revokeDocumentPermissionRequest,
  type DocumentPermissionLevel,
  type PermissionGrant,
  type UserSearchHit,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface DocumentPermissionsPanelProps {
  documentId: string;
  /** Only document owners may manage sharing. */
  canManage: boolean;
  /** Document owner id — excluded from recipient search (cannot grant to owner). */
  ownerUserId?: string;
}

export function DocumentPermissionsPanel({
  documentId,
  canManage,
  ownerUserId,
}: DocumentPermissionsPanelProps) {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const permissionId = useId();

  const [grants, setGrants] = useState<PermissionGrant[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [selectedUser, setSelectedUser] = useState<UserSearchHit | null>(null);
  const [permission, setPermission] = useState<DocumentPermissionLevel>("READ");
  const [granting, setGranting] = useState(false);
  const [changingUserId, setChangingUserId] = useState<string | null>(null);

  const [revokeTarget, setRevokeTarget] = useState<PermissionGrant | null>(null);
  const [revoking, setRevoking] = useState(false);

  const loadGrants = useCallback(async () => {
    if (!accessToken || !canManage) return;
    try {
      const data = await listDocumentPermissionsRequest(accessToken, documentId);
      setGrants(data.permissions);
      setStatus("ready");
      setError(null);
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setGrants([]);
      setError(
        err instanceof ApiError ? err.detail : "Unable to load permissions.",
      );
      setStatus("error");
    }
  }, [accessToken, canManage, documentId, handleUnauthorized]);

  useEffect(() => {
    if (!canManage || !accessToken) return;
    const token = accessToken;
    const id = documentId;
    void (async () => {
      setStatus("loading");
      setError(null);
      try {
        const data = await listDocumentPermissionsRequest(token, id);
        setGrants(data.permissions);
        setStatus("ready");
      } catch (err) {
        if (handleUnauthorized(err)) return;
        setGrants([]);
        setError(
          err instanceof ApiError ? err.detail : "Unable to load permissions.",
        );
        setStatus("error");
      }
    })();
  }, [accessToken, canManage, documentId, handleUnauthorized]);

  // Recipients do not need an instructional "you cannot share" panel.
  if (!canManage) return null;

  async function onGrant(event: FormEvent) {
    event.preventDefault();
    if (!accessToken || granting) return;
    if (!selectedUser) {
      setError("Select a registered recipient from search results.");
      return;
    }
    if (ownerUserId && selectedUser.id === ownerUserId) {
      setError("Cannot grant access to the document owner.");
      return;
    }
    setGranting(true);
    setError(null);
    setMessage(null);
    try {
      await grantDocumentPermissionRequest(accessToken, documentId, {
        user_id: selectedUser.id,
        permission,
      });
      setMessage(
        `Granted ${permission} access to ${selectedUser.name} (${selectedUser.email}).`,
      );
      setSelectedUser(null);
      await loadGrants();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      const detail =
        err instanceof ApiError ? err.detail : "Grant failed.";
      if (/already exists/i.test(detail)) {
        setError(
          `${selectedUser.name} already has this permission. Use Change on their row to switch READ ↔ EDIT.`,
        );
      } else if (/owner/i.test(detail)) {
        setError("Cannot grant access to the document owner.");
      } else if (/inactive/i.test(detail)) {
        setError("That account is inactive and cannot receive access.");
      } else if (/not found/i.test(detail)) {
        setError("That user was not found. Search again and reselect.");
      } else {
        setError(detail);
      }
    } finally {
      setGranting(false);
    }
  }

  async function changePermission(
    grant: PermissionGrant,
    next: DocumentPermissionLevel,
  ) {
    if (!accessToken || changingUserId || grant.permission === next) return;
    setChangingUserId(grant.user.id);
    setError(null);
    setMessage(null);
    try {
      await grantDocumentPermissionRequest(accessToken, documentId, {
        user_id: grant.user.id,
        permission: next,
      });
      setMessage(
        `Updated ${grant.user.name} from ${grant.permission} to ${next}.`,
      );
      await loadGrants();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(
        err instanceof ApiError ? err.detail : "Unable to change permission.",
      );
    } finally {
      setChangingUserId(null);
    }
  }

  async function confirmRevoke() {
    if (!accessToken || !revokeTarget || revoking) return;
    setRevoking(true);
    setError(null);
    setMessage(null);
    try {
      await revokeDocumentPermissionRequest(
        accessToken,
        documentId,
        revokeTarget.user.id,
      );
      setMessage(
        `Revoked ${revokeTarget.permission} for ${revokeTarget.user.name} (${revokeTarget.user.email}).`,
      );
      setRevokeTarget(null);
      await loadGrants();
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setError(err instanceof ApiError ? err.detail : "Revoke failed.");
      setRevokeTarget(null);
    } finally {
      setRevoking(false);
    }
  }

  return (
    <section
      aria-label="Permission management"
      className="rounded-[var(--radius)] border border-border bg-surface p-5 shadow-[var(--shadow-sm)] sm:p-6"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-strong">
          <Share2 className="h-5 w-5" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="font-accent text-lg font-semibold tracking-tight text-foreground">
            Sharing
          </h2>
          <p className="mt-1 text-sm text-muted">
            Grant access to registered users. Metadata, delete, and sharing stay
            owner-only.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-[0.75rem] border border-border bg-accent-soft/40 px-3 py-3">
          <p className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent-strong">
            <Shield className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            READ
          </p>
          <p className="mt-1 text-sm text-muted">
            Preview and download PDF through the TrustVault API.
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border bg-accent-soft/40 px-3 py-3">
          <p className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent-strong">
            <Shield className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            EDIT
          </p>
          <p className="mt-1 text-sm text-muted">
            Everything in READ, plus DOCX body editing when supported.
          </p>
        </div>
      </div>

      <form
        onSubmit={(event) => void onGrant(event)}
        className="mt-5 space-y-3"
      >
        <UserSearchPicker
          selected={selectedUser}
          onSelect={setSelectedUser}
          disabled={granting}
          excludeUserIds={ownerUserId ? [ownerUserId] : []}
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="block min-w-0 flex-1 sm:max-w-[12rem]">
            <label htmlFor={permissionId} className="tv-label">
              Permission
            </label>
            <select
              id={permissionId}
              value={permission}
              onChange={(event) =>
                setPermission(event.target.value as DocumentPermissionLevel)
              }
              disabled={granting}
              className="tv-input disabled:opacity-60"
            >
              <option value="READ">READ</option>
              <option value="EDIT">EDIT</option>
            </select>
          </div>
          <Button
            type="submit"
            variant="primary"
            disabled={granting || !selectedUser}
            title={
              !selectedUser
                ? "Select a recipient from search results first"
                : undefined
            }
            className="w-full sm:w-auto"
          >
            {granting ? (
              <>
                <LoaderCircle
                  className="h-4 w-4 animate-spin"
                  strokeWidth={1.75}
                  aria-hidden
                />
                Granting…
              </>
            ) : (
              "Grant access"
            )}
          </Button>
        </div>
      </form>

      {error ? <div className="mt-3"><Alert tone="error">{error}</Alert></div> : null}
      {message ? (
        <div className="mt-3">
          <Alert tone="success">{message}</Alert>
        </div>
      ) : null}

      {status === "loading" ? (
        <p className="mt-4 text-sm text-muted" role="status">
          Loading grants…
        </p>
      ) : null}

      {status === "error" ? (
        <div className="mt-4">
          <Button size="sm" variant="secondary" onClick={() => void loadGrants()}>
            Retry loading grants
          </Button>
        </div>
      ) : null}

      {status === "ready" && grants.length === 0 ? (
        <p className="mt-4 text-sm text-muted">
          No active grants. Search for a registered user to share this document.
        </p>
      ) : null}

      {status === "ready" && grants.length > 0 ? (
        <ul className="mt-4 divide-y divide-border overflow-hidden rounded-[0.75rem] border border-border">
          {grants.map((grant) => {
            const nextLevel: DocumentPermissionLevel =
              grant.permission === "READ" ? "EDIT" : "READ";
            const changing = changingUserId === grant.user.id;
            return (
              <li
                key={grant.id}
                className="flex flex-wrap items-center justify-between gap-3 bg-surface px-3 py-3 text-sm"
              >
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-foreground">
                    <span className="truncate">{grant.user.name}</span>
                    <Badge
                      tone={grant.permission === "EDIT" ? "accent" : "neutral"}
                    >
                      {grant.permission}
                    </Badge>
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {grant.user.email} · since {formatDateTime(grant.granted_at)}
                    {grant.regranted ? " · regranted" : ""}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={changing || revoking || granting}
                    onClick={() => void changePermission(grant, nextLevel)}
                  >
                    {changing ? "Updating…" : `Change to ${nextLevel}`}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="danger"
                    disabled={changing || revoking || granting}
                    onClick={() => setRevokeTarget(grant)}
                  >
                    Revoke
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}

      <ConfirmDialog
        open={revokeTarget !== null}
        title="Revoke access?"
        description={
          revokeTarget
            ? `Remove ${revokeTarget.permission} access for ${revokeTarget.user.email}? Their next document request will be denied.`
            : ""
        }
        confirmLabel="Confirm revoke"
        danger
        busy={revoking}
        onCancel={() => {
          if (!revoking) setRevokeTarget(null);
        }}
        onConfirm={() => void confirmRevoke()}
      />
    </section>
  );
}
