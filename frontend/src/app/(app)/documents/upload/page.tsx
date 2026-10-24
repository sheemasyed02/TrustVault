"use client";

import { Upload } from "lucide-react";
import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { UploadDocumentForm } from "@/components/upload-document-form";
import { buttonClassName } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";

export default function UploadDocumentPage() {
  const { user } = useAuth();

  if (!user) return null;

  if (user.role !== "OWNER") {
    return (
      <EmptyState
        title="Upload unavailable"
        description="Only OWNER accounts can upload. The API rejects other roles with 403."
        icon={<Upload className="h-5 w-5" strokeWidth={1.75} />}
        action={
          <Link
            href="/dashboard"
            className={buttonClassName({ variant: "secondary" })}
          >
            Back to dashboard
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Upload document"
        description="Microsoft Word DOCX only. Files go to private storage through the API; downloads are converted to PDF from the latest saved file."
      />
      <Panel>
        <UploadDocumentForm />
      </Panel>
    </div>
  );
}
