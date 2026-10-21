import type { DocumentDetail, DocumentAccessLevel, UserPublic } from "@/lib/api";

export interface DocumentUiAccess {
  isOwner: boolean;
  yourAccess: DocumentAccessLevel;
  /** Owner or EDIT grantee — metadata and in-app content editing. */
  canEditDocument: boolean;
  canManageSharing: boolean;
  canDelete: boolean;
}

/**
 * Human label for document-level `your_access`.
 * Distinct from platform roles ADMIN / OWNER / VIEWER.
 */
export function formatDocumentAccessLabel(level: DocumentAccessLevel): string {
  if (level === "OWNER") return "Document owner";
  if (level === "EDIT") return "EDIT grant";
  return "READ grant";
}

/**
 * UI capability hints from server-provided `your_access`.
 * Never invent OWNER/EDIT from the client platform role alone.
 * Document OWNER here means documents.owner_id, not users.role=OWNER.
 */
export function getDocumentUiAccess(
  user: UserPublic,
  doc: DocumentDetail,
): DocumentUiAccess {
  const yourAccess = doc.your_access;
  const isOwner = yourAccess === "OWNER" || doc.owner.id === user.id;
  const canEditDocument = yourAccess === "OWNER" || yourAccess === "EDIT";
  return {
    isOwner,
    yourAccess,
    canEditDocument,
    canManageSharing: isOwner,
    canDelete: isOwner,
  };
}
