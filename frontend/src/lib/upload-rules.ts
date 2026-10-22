/** Client-side upload hints mirroring backend file_validation (not a security boundary). */

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10 MiB

export const ALLOWED_EXTENSIONS = [".docx"] as const;

export const DOCX_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** Legacy stored documents / PDF download MIME — not accepted for new uploads. */
export const PDF_MIME_TYPE = "application/pdf";

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
  const mimeOk = (ALLOWED_MIME_TYPES as readonly string[]).includes(file.type);
  const extOk = (ALLOWED_EXTENSIONS as readonly string[]).includes(ext);
  if (!extOk && !mimeOk) {
    return "Only DOCX documents are allowed. PDF and other formats are rejected by the server.";
  }
  if (ext === ".pdf" || file.type === PDF_MIME_TYPE) {
    return "Only DOCX documents are allowed. PDF uploads are not accepted.";
  }
  if (!extOk) {
    return "Only DOCX documents are allowed. The server also checks file content.";
  }
  return null;
}
