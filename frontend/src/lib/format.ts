export function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size < 0) return "—";
  if (size < 1024) return `${size} B`;
  const units = ["KB", "MB", "GB"];
  let value = size / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function mimeLabel(mime: string): string {
  const map: Record<string, string> = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
      "DOCX",
    // Legacy labels for older uploads that are no longer accepted.
    "application/pdf": "PDF (legacy)",
    "image/png": "PNG (legacy)",
    "image/jpeg": "JPEG (legacy)",
  };
  return map[mime] ?? mime;
}
