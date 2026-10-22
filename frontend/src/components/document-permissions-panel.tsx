"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
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

  if (!canManage) {
    return (
      <section className="rounded-xl border border-border bg-surface p-5 text-sm text-muted shadow-[var(--shadow)]">
        <h2 className="font-display text-xl text-foreground">Sharing</h2>
        <p className="mt-2">
          Only the document owner can grant or revoke access. Recipients with
          EDIT cannot manage sharing.
        </p>
      </section>
    );
  }

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
      className="rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow)]"
    >
      <h2 className="font-display text-xl text-foreground">Sharing</h2>
      <p className="mt-1 text-sm text-muted">
        <strong className="font-semibold text-foreground">READ</strong> allows
        preview and download.{" "}
        <strong className="font-semibold text-foreground">EDIT</strong> also
        allows supported content editing (DOCX text). Metadata, delete, and
        sharing stay owner-only. Grants never change platform roles. Revocation
        blocks the next server request; copies already downloaded locally are
        outside TrustVault control.
      </p>

      <form
        onSubmit={(event) => void onGrant(event)}
        className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]"
      >
        <div className="sm:col-span-1">
          <UserSearchPicker
            selected={selectedUser}
            onSelect={setSelectedUser}
            disabled={granting}
            excludeUserIds={ownerUserId ? [ownerUserId] : []}
          />
        </div>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Permission</span>
          <select
            value={permission}
            onChange={(event) =>
              setPermission(event.target.value as DocumentPermissionLevel)
            }
            disabled={granting}
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-60"
          >
            <option value="READ">READ</option>
            <option value="EDIT">EDIT</option>
          </select>
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={granting || !selectedUser}
            title={
              !selectedUser
                ? "Select a recipient from search results first"
                : undefined
            }
            className="w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
          >
            {granting ? "Granting…" : "Grant access"}
          </button>
        </div>
      </form>

      {error ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="mt-3 text-sm text-accent-strong">
          {message}
        </p>
      ) : null}

      {status === "loading" ? (
        <p className="mt-4 text-sm text-muted" role="status">
          Loading grants…
        </p>
      ) : null}

      {status === "error" ? (
        <button
          type="button"
          onClick={() => void loadGrants()}
          className="mt-4 text-sm font-semibold text-danger underline"
        >
          Retry loading grants
        </button>
      ) : null}

      {status === "ready" && grants.length === 0 ? (
        <p className="mt-4 text-sm text-muted">
          No active grants. Search for a registered user to share this document.
        </p>
      ) : null}

      {status === "ready" && grants.length > 0 ? (
        <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
          {grants.map((grant) => {
            const nextLevel: DocumentPermissionLevel =
              grant.permission === "READ" ? "EDIT" : "READ";
            const changing = changingUserId === grant.user.id;
            return (
              <li
                key={grant.id}
                className="flex flex-wrap items-center justify-between gap-3 px-3 py-3 text-sm"
              >
                <div>
                  <p className="font-medium text-foreground">
                    {grant.user.name}{" "}
                    <span
                      className={`ml-2 rounded px-1.5 py-0.5 text-xs font-semibold ${
                        grant.permission === "EDIT"
                          ? "bg-accent-soft text-accent-strong"
                          : "bg-white text-muted"
                      }`}
                    >
                      {grant.permission}
                    </span>
                  </p>
                  <p className="text-xs text-muted">
                    {grant.user.email} · since {formatDateTime(grant.granted_at)}
                    {grant.regranted ? " · regranted" : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={changing || revoking}
                    onClick={() => void changePermission(grant, nextLevel)}
                    className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {changing ? "Updating…" : `Change to ${nextLevel}`}
                  </button>
                  <button
                    type="button"
                    disabled={changing || revoking}
                    onClick={() => setRevokeTarget(grant)}
                    className="rounded-md border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Revoke
                  </button>
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
