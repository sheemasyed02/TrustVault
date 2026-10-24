"use client";

import { AlertTriangle, RefreshCw, ShieldCheck, ShieldQuestion } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import {
  ApiError,
  verifyAuditIntegrityRequest,
  type AuditIntegrityResult,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

/**
 * Separate from Audit Logs: answers whether the hash chain verifies,
 * not what individual events occurred.
 */
export default function AdminAuditIntegrityPage() {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const [result, setResult] = useState<AuditIntegrityResult | null>(null);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">(
    "idle",
  );

  async function onVerify() {
    if (!accessToken || status === "running") return;
    setStatus("running");
    setError(null);
    try {
      const data = await verifyAuditIntegrityRequest(accessToken);
      setResult(data);
      setCheckedAt(new Date().toISOString());
      setStatus("done");
    } catch (err) {
      if (handleUnauthorized(err)) return;
      setResult(null);
      setError(
        err instanceof ApiError
          ? err.detail
          : "Integrity verification request failed.",
      );
      setStatus("error");
    }
  }

  const neverRun = status === "idle" && !result;
  const failedRequest = status === "error";
  const isRunning = status === "running";

  return (
    <div className="space-y-5">
      <Link
        href="/admin"
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← Admin dashboard
      </Link>

      <PageHeader
        title="Audit integrity"
        description={
          <>
            Checks whether persisted audit records pass the application&apos;s
            hash-chain verification. This page does not list individual events —
            use{" "}
            <Link
              href="/admin/audit"
              className="font-semibold text-accent-strong underline"
            >
              Audit Logs
            </Link>{" "}
            for that. A same-database hash chain is not tamper-proof against a
            privileged operator who can rewrite records and hashes together.
          </>
        }
        actions={
          <Button
            type="button"
            variant="primary"
            onClick={() => void onVerify()}
            disabled={isRunning}
            aria-busy={isRunning}
          >
            {isRunning ? (
              <>
                <RefreshCw
                  className="h-3.5 w-3.5 animate-spin"
                  strokeWidth={1.75}
                  aria-hidden
                />
                Verifying...
              </>
            ) : (
              <>
                <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                Run integrity check
              </>
            )}
          </Button>
        }
      />

      {neverRun ? (
        <section
          className="rounded-[var(--radius)] border border-dashed border-border bg-surface px-6 py-10 text-center shadow-[var(--shadow-sm)]"
          role="status"
        >
          <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent-strong">
            <ShieldQuestion className="h-5 w-5" strokeWidth={1.75} aria-hidden />
          </span>
          <p className="mt-3 font-semibold text-foreground">Not verified yet</p>
          <p className="mt-2 text-sm text-muted">
            No check has run yet. Run the integrity check to verify previous_hash
            links and recalculated event hashes for the current audit chain.
          </p>
          <Badge tone="neutral" className="mt-4">
            Pending verification
          </Badge>
        </section>
      ) : null}

      {failedRequest ? (
        <Alert tone="error" title="Verification could not complete">
          {error}
        </Alert>
      ) : null}

      {result ? (
        <Panel
          className={
            result.valid
              ? "border-success/30 bg-[color-mix(in_srgb,var(--success)_6%,white)]"
              : "border-danger/30 bg-[color-mix(in_srgb,var(--danger)_6%,white)]"
          }
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                Integrity status
              </p>
              <h2
                className={`mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight ${
                  result.valid ? "text-success" : "text-danger"
                }`}
              >
                {result.valid ? (
                  <ShieldCheck className="h-6 w-6" strokeWidth={1.75} aria-hidden />
                ) : (
                  <AlertTriangle className="h-6 w-6" strokeWidth={1.75} aria-hidden />
                )}
                {result.valid ? "Check passed" : "Check failed"}
              </h2>
            </div>
            <Badge tone={result.valid ? "success" : "danger"}>
              {result.valid ? "Passed" : "Failed"}
            </Badge>
          </div>

          <div className="mt-4">
            {!result.valid ? (
              <Alert tone="warning" title="Chain verification warning">
                {result.detail}
                {result.reason_code ? (
                  <span className="mt-1 block text-xs">
                    Reason code: {result.reason_code}
                  </span>
                ) : null}
              </Alert>
            ) : (
              <p className="text-sm text-foreground" role="status">
                {result.detail}
                {result.reason_code ? (
                  <span className="mt-1 block text-xs text-muted">
                    Reason code: {result.reason_code}
                  </span>
                ) : null}
              </p>
            )}
          </div>

          <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Events in chain" value={String(result.event_count)} />
            <Metric
              label="Events checked"
              value={String(result.checked_count)}
            />
            <Metric
              label="First failure index"
              value={
                result.first_failure_index === null
                  ? "—"
                  : String(result.first_failure_index)
              }
            />
            <Metric
              label="Last run"
              value={checkedAt ? formatDateTime(checkedAt) : "—"}
            />
          </dl>

          {result.first_failure_event_id ? (
            <p className="mt-4 break-all font-mono text-xs text-muted">
              First failing event id: {result.first_failure_event_id}
            </p>
          ) : null}

          <p className="mt-5 text-xs leading-5 text-muted">
            A successful check means the stored chain matched the verifier at this
            moment. It does not prove the audit log is impossible to tamper with.
          </p>
        </Panel>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[0.75rem] border border-border bg-surface px-3 py-3">
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 text-sm font-semibold text-foreground">{value}</dd>
    </div>
  );
}
