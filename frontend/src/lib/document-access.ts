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
 * UI capability hints from server-provided `your_access`.
 * Never invent OWNER/EDIT from the client role alone.
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
