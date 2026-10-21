/** Client-side upload hints mirroring backend file_validation (not a security boundary). */

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10 MiB

/** TrustVault accepts editable Word documents only. */
export const ALLOWED_EXTENSIONS = [".docx"] as const;

export const DOCX_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export const ALLOWED_MIME_TYPES = [DOCX_MIME_TYPE] as const;

export function fileExtension(name: string): string {
  const idx = name.lastIndexOf(".");
  if (idx < 0) return "";
  return name.slice(idx).toLowerCase();
}

export function validateUploadFileClient(file: File | null): string | null {
  if (!file) return "Choose a file to upload.";
  if (file.size <= 0) return "The selected file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    return "File exceeds the 10 MiB size limit.";
  }
  const ext = fileExtension(file.name);
  if (
    !(ALLOWED_EXTENSIONS as readonly string[]).includes(ext) &&
    !(ALLOWED_MIME_TYPES as readonly string[]).includes(file.type)
  ) {
    return "Only DOCX Word documents are allowed. The server also checks file content.";
  }
  return null;
}
