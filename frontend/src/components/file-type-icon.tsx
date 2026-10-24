import { FileText, FileType2, Image as ImageIcon } from "lucide-react";

/** Consistent Lucide icon for known document MIME types (no remote/thumbnail assets). */
export function FileTypeIcon({
  mime,
  className = "h-4 w-4",
}: {
  mime: string;
  className?: string;
}) {
  const props = {
    className,
    strokeWidth: 1.75 as const,
    "aria-hidden": true as const,
  };

  if (
    mime ===
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ) {
    return <FileText {...props} />;
  }
  if (mime === "application/pdf") {
    return <FileType2 {...props} />;
  }
  if (mime.startsWith("image/")) {
    return <ImageIcon {...props} />;
  }
  return <FileText {...props} />;
}
