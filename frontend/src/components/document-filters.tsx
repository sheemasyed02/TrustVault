"use client";

import { useEffect, useState } from "react";

export interface DocumentFilterValues {
  title: string;
  category: string;
  createdFrom: string;
  createdTo: string;
}

interface DocumentFiltersProps {
  value: DocumentFilterValues;
  onChange: (next: DocumentFilterValues) => void;
  showOwnerHint?: string | null;
}

export function DocumentFilters({
  value,
  onChange,
  showOwnerHint,
}: DocumentFiltersProps) {
  const [titleInput, setTitleInput] = useState(value.title);
  const [titleFromProps, setTitleFromProps] = useState(value.title);
  const [rangeError, setRangeError] = useState<string | null>(null);

  if (value.title !== titleFromProps) {
    setTitleFromProps(value.title);
    setTitleInput(value.title);
  }

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (titleInput !== value.title) {
        onChange({ ...value, title: titleInput });
      }
    }, 350);
    return () => window.clearTimeout(handle);
  }, [titleInput, value, onChange]);

  function applyDates(createdFrom: string, createdTo: string) {
    if (createdFrom && createdTo && createdFrom > createdTo) {
      setRangeError("Start date must be on or before end date.");
      return;
    }
    setRangeError(null);
    onChange({ ...value, createdFrom, createdTo });
  }

  const hasActive =
    Boolean(value.title) ||
    Boolean(value.category) ||
    Boolean(value.createdFrom) ||
    Boolean(value.createdTo);

  return (
    <section
      aria-label="Search and filters"
      className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow)]"
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Title search</span>
          <input
            type="search"
            value={titleInput}
            onChange={(event) => setTitleInput(event.target.value)}
            placeholder="Search titles"
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Category</span>
          <input
            type="text"
            value={value.category}
            onChange={(event) =>
              onChange({ ...value, category: event.target.value })
            }
            placeholder="Exact category"
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Created from</span>
          <input
            type="date"
            value={value.createdFrom}
            onChange={(event) =>
              applyDates(event.target.value, value.createdTo)
            }
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Created to</span>
          <input
            type="date"
            value={value.createdTo}
            onChange={(event) =>
              applyDates(value.createdFrom, event.target.value)
            }
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          />
        </label>
      </div>

      {showOwnerHint ? (
        <p className="mt-3 text-xs text-muted">{showOwnerHint}</p>
      ) : null}
      {rangeError ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {rangeError}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {hasActive ? (
          <p className="text-xs text-muted">
            Active filters:
            {value.title ? ` title “${value.title}”` : ""}
            {value.category ? ` category “${value.category}”` : ""}
            {value.createdFrom ? ` from ${value.createdFrom}` : ""}
            {value.createdTo ? ` to ${value.createdTo}` : ""}
          </p>
        ) : (
          <p className="text-xs text-muted">No filters active</p>
        )}
        <button
          type="button"
          disabled={!hasActive}
          onClick={() => {
            setTitleInput("");
            setTitleFromProps("");
            setRangeError(null);
            onChange({
              title: "",
              category: "",
              createdFrom: "",
              createdTo: "",
            });
          }}
          className="ml-auto rounded-md border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
        >
          Clear filters
        </button>
      </div>
    </section>
  );
}

export function toApiDateBound(date: string, endOfDay: boolean): string | undefined {
  if (!date) return undefined;
  return endOfDay ? `${date}T23:59:59.999Z` : `${date}T00:00:00.000Z`;
}
