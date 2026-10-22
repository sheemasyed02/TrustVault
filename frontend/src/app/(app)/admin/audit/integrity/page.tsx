"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
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

  return (
    <div className="space-y-5">
      <Link
        href="/admin"
        className="text-sm font-semibold text-accent-strong hover:underline"
      >
        ← Admin dashboard
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
            Administration
          </p>
          <h1 className="mt-2 font-display text-3xl tracking-tight text-foreground">
            Audit integrity
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Answers: are persisted audit records passing the application&apos;s
            hash-chain checks? This page does not list individual events — use{" "}
            <Link
              href="/admin/audit"
              className="font-semibold text-accent-strong underline"
            >
              Audit Logs
            </Link>{" "}
            for that. A same-database hash chain is not tamper-proof against a
            privileged DBA who can rewrite records and hashes together.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void onVerify()}
          disabled={status === "running"}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
        >
          {status === "running" ? "Verifying…" : "Run integrity check"}
        </button>
      </header>

      {neverRun ? (
        <section
          className="rounded-xl border border-dashed border-border bg-surface px-6 py-10 text-center shadow-[var(--shadow)]"
          role="status"
        >
          <p className="font-medium text-foreground">No check has run yet</p>
          <p className="mt-2 text-sm text-muted">
            Run the integrity check to verify previous_hash links and recalculated
            event hashes for the current audit chain.
          </p>
        </section>
      ) : null}

      {failedRequest ? (
        <div
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-4 text-sm text-danger"
        >
          <p className="font-semibold">Verification could not complete</p>
          <p className="mt-1">{error}</p>
        </div>
      ) : null}

      {result ? (
        <section
          className={`rounded-xl border px-5 py-5 shadow-[var(--shadow)] ${
            result.valid
              ? "border-accent/30 bg-accent-soft/40"
              : "border-danger/30 bg-danger/5"
          }`}
          role="status"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">
            Integrity status
          </p>
          <h2
            className={`mt-1 font-display text-2xl ${
              result.valid ? "text-accent-strong" : "text-danger"
            }`}
          >
            {result.valid ? "Check passed" : "Check failed"}
          </h2>
          <p className="mt-2 text-sm text-foreground">{result.detail}</p>
          {result.reason_code ? (
            <p className="mt-1 text-xs text-muted">
              Reason code: {result.reason_code}
            </p>
          ) : null}

          <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
        </section>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-surface/80 px-3 py-3">
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 text-sm font-semibold text-foreground">{value}</dd>
    </div>
  );
}
