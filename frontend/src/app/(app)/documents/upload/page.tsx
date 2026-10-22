"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { UploadDocumentForm } from "@/components/upload-document-form";

export default function UploadDocumentPage() {
  const { user } = useAuth();

  if (!user) return null;

  if (user.role !== "OWNER") {
    return (
      <div className="rounded-xl border border-border bg-surface p-6">
        <h1 className="font-display text-2xl">Upload unavailable</h1>
        <p className="mt-2 text-sm text-muted">
          Only OWNER accounts can upload. The API rejects other roles with 403.
        </p>
        <Link
          href="/dashboard"
          className="mt-4 inline-block text-sm font-semibold text-accent-strong"
        >
          Back to dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <header>
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Upload
        </p>
        <h1 className="mt-2 font-display text-3xl tracking-tight">
          Upload document
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Upload Microsoft Word DOCX files only (PDF is rejected by the API).
          Files go to private storage through{" "}
          <code className="text-xs">POST /documents</code>. Storage keys and
          credentials are never returned to the browser. Authorized users edit
          DOCX content in-app; downloads are converted to PDF from the latest
          saved DOCX.
        </p>
      </header>
      <UploadDocumentForm />
    </div>
  );
}
