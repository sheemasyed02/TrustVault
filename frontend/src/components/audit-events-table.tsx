"use client";

import { Fragment, useState } from "react";

import type { AuditEventItem } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

function truncate(value: string, max = 36): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const isSuccess = outcome === "SUCCESS";
  const isDenied = outcome === "DENIED";
  return (
    <span
      className={`inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ${
        isSuccess
          ? "bg-accent-soft text-accent-strong"
          : isDenied
            ? "bg-danger/10 text-danger"
            : "bg-muted/20 text-muted"
      }`}
    >
      {isSuccess ? "Success" : isDenied ? "Denied" : outcome}
    </span>
  );
}

function PersonCell({
  name,
  email,
  id,
}: {
  name?: string | null;
  email?: string | null;
  id?: string | null;
}) {
  if (!name && !email && !id) return <span className="text-muted">—</span>;
  const primary = email || name || id || "—";
  const title = [name, email, id].filter(Boolean).join(" · ");
  return (
    <span className="block max-w-[14rem] truncate" title={title}>
      {name && email ? (
        <>
          <span className="font-medium text-foreground">{truncate(name, 24)}</span>
          <span className="mt-0.5 block truncate text-xs text-muted">
            {truncate(email, 28)}
          </span>
        </>
      ) : (
        <span className="text-foreground">{truncate(primary, 32)}</span>
      )}
    </span>
  );
}

interface AuditEventsTableProps {
  events: AuditEventItem[];
  emptyMessage?: string;
}

export function AuditEventsTable({
  events,
  emptyMessage = "No audit events match these filters.",
}: AuditEventsTableProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (events.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-12 text-center">
        <p className="font-medium text-foreground">{emptyMessage}</p>
        <p className="mt-2 text-sm text-muted">
          Adjust filters or wait for new security-relevant activity.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-[var(--shadow)]">
      {/* Desktop table */}
      <div className="hidden overflow-x-auto lg:block">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border bg-accent-soft/30 text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-3 font-semibold">When</th>
              <th className="px-4 py-3 font-semibold">Action</th>
              <th className="px-4 py-3 font-semibold">Outcome</th>
              <th className="px-4 py-3 font-semibold">Actor</th>
              <th className="px-4 py-3 font-semibold">Document</th>
              <th className="px-4 py-3 font-semibold">Reason</th>
              <th className="px-4 py-3 font-semibold">
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => {
              const open = expandedId === event.id;
              const whenLabel = formatDateTime(event.created_at);
              return (
                <Fragment key={event.id}>
                  <tr className="border-b border-border/70 align-top">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <time
                        dateTime={event.created_at}
                        title={event.created_at}
                        className="text-foreground"
                      >
                        {whenLabel}
                      </time>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-foreground">
                        {event.action.replaceAll("_", " ")}
                      </span>
                      {event.is_owner_self_view ? (
                        <span className="mt-1 block text-xs text-muted">
                          Owner self-view
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <OutcomeBadge outcome={event.outcome} />
                    </td>
                    <td className="px-4 py-3">
                      <PersonCell
                        name={event.actor_name}
                        email={event.actor_email}
                        id={event.actor_id}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {event.document_title || event.document_id ? (
                        <span className="block max-w-[14rem]">
                          <span
                            className="block truncate font-medium text-foreground"
                            title={event.document_title ?? undefined}
                          >
                            {event.document_title
                              ? truncate(event.document_title, 40)
                              : "Document"}
                          </span>
                          {event.document_owner_email ? (
                            <span className="mt-0.5 block truncate text-xs text-muted">
                              Owner: {truncate(event.document_owner_email, 28)}
                            </span>
                          ) : null}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="block max-w-[10rem] truncate text-muted"
                        title={event.reason_code ?? undefined}
                      >
                        {event.reason_code
                          ? truncate(event.reason_code, 24)
                          : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedId(open ? null : event.id)
                        }
                        className="text-xs font-semibold text-accent-strong hover:underline"
                        aria-expanded={open}
                      >
                        {open ? "Hide" : "Details"}
                      </button>
                    </td>
                  </tr>
                  {open ? (
                    <tr className="border-b border-border/70 bg-accent-soft/20">
                      <td colSpan={7} className="px-4 py-4">
                        <EventDetails event={event} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <ul className="divide-y divide-border lg:hidden">
        {events.map((event) => {
          const open = expandedId === event.id;
          return (
            <li key={event.id} className="px-4 py-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-foreground">
                    {event.action.replaceAll("_", " ")}
                  </p>
                  <p className="mt-1 text-xs text-muted" title={event.created_at}>
                    {formatDateTime(event.created_at)}
                  </p>
                </div>
                <OutcomeBadge outcome={event.outcome} />
              </div>
              <dl className="mt-3 space-y-2 text-sm">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-muted">
                    Actor
                  </dt>
                  <dd className="mt-0.5">
                    <PersonCell
                      name={event.actor_name}
                      email={event.actor_email}
                      id={event.actor_id}
                    />
                  </dd>
                </div>
                {(event.document_title || event.document_id) && (
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-muted">
                      Document
                    </dt>
                    <dd className="mt-0.5 text-foreground">
                      {event.document_title ?? event.document_id}
                    </dd>
                  </div>
                )}
              </dl>
              <button
                type="button"
                onClick={() => setExpandedId(open ? null : event.id)}
                className="mt-3 text-xs font-semibold text-accent-strong hover:underline"
              >
                {open ? "Hide details" : "Show details"}
              </button>
              {open ? <EventDetails event={event} /> : null}
            </li>
          );
        })}
      </ul>

    </div>
  );
}

function EventDetails({ event }: { event: AuditEventItem }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Detail label="Event ID" value={event.id} mono />
      <Detail label="UTC timestamp" value={event.created_at} mono />
      <Detail label="Request ID" value={event.request_id} mono />
      <Detail label="Actor ID" value={event.actor_id} mono />
      <Detail
        label="Target"
        value={
          event.target_user_email ||
          event.target_user_name ||
          event.target_user_id
        }
      />
      <Detail label="Document ID" value={event.document_id} mono />
      <Detail label="Document owner" value={event.document_owner_email} />
      <Detail label="Reason" value={event.reason_code} />
      <Detail
        label="Event hash"
        value={event.event_hash ? truncate(event.event_hash, 20) : null}
        mono
        title={event.event_hash ?? undefined}
      />
    </dl>
  );
}

function Detail({
  label,
  value,
  mono,
  title,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
  title?: string;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd
        className={`mt-1 break-all text-foreground ${mono ? "font-mono text-xs" : ""}`}
        title={title}
      >
        {value?.trim() ? value : "—"}
      </dd>
    </div>
  );
}
