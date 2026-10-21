import { describe, expect, it } from "vitest";

import {
  DOCX_MIME_TYPE,
  MAX_UPLOAD_BYTES,
  validateUploadFileClient,
} from "@/lib/upload-rules";

describe("validateUploadFileClient", () => {
  it("rejects missing, empty, oversized, and non-DOCX types", () => {
    expect(validateUploadFileClient(null)).toMatch(/choose a file/i);
    expect(
      validateUploadFileClient(
        new File([], "empty.docx", { type: DOCX_MIME_TYPE }),
      ),
    ).toMatch(/empty/i);

    const oversized = new File(
      [new Uint8Array(MAX_UPLOAD_BYTES + 1)],
      "big.docx",
      { type: DOCX_MIME_TYPE },
    );
    expect(validateUploadFileClient(oversized)).toMatch(/10 MiB/i);

    expect(
      validateUploadFileClient(
        new File(["x"], "notes.exe", { type: "application/octet-stream" }),
      ),
    ).toMatch(/DOCX/i);

    expect(
      validateUploadFileClient(
        new File(["%PDF"], "a.pdf", { type: "application/pdf" }),
      ),
    ).toMatch(/DOCX/i);

    expect(
      validateUploadFileClient(
        new File(["x"], "a.png", { type: "image/png" }),
      ),
    ).toMatch(/DOCX/i);
  });

  it("accepts a typical DOCX selection (client-side only)", () => {
    expect(
      validateUploadFileClient(
        new File(["PK"], "report.docx", { type: DOCX_MIME_TYPE }),
      ),
    ).toBeNull();
  });
});
