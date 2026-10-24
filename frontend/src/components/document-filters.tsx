"use client";

import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

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
      className="rounded-[var(--radius)] border border-border bg-surface p-4 shadow-[var(--shadow-sm)] sm:p-5"
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="block text-sm">
          <span className="tv-label">Title search</span>
          <span className="relative block">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
              strokeWidth={1.75}
              aria-hidden
            />
            <input
              type="search"
              value={titleInput}
              onChange={(event) => setTitleInput(event.target.value)}
              placeholder="Search titles"
              className="tv-input pl-9"
            />
          </span>
        </label>
        <label className="block text-sm">
          <span className="tv-label">Category</span>
          <input
            type="text"
            value={value.category}
            onChange={(event) =>
              onChange({ ...value, category: event.target.value })
            }
            placeholder="Exact category"
            className="tv-input"
          />
        </label>
        <label className="block text-sm">
          <span className="tv-label">Created from</span>
          <input
            type="date"
            value={value.createdFrom}
            onChange={(event) =>
              applyDates(event.target.value, value.createdTo)
            }
            className="tv-input"
          />
        </label>
        <label className="block text-sm">
          <span className="tv-label">Created to</span>
          <input
            type="date"
            value={value.createdTo}
            onChange={(event) =>
              applyDates(value.createdFrom, event.target.value)
            }
            className="tv-input"
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
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={!hasActive}
          className="ml-auto"
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
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          Clear filters
        </Button>
      </div>
    </section>
  );
}

export function toApiDateBound(date: string, endOfDay: boolean): string | undefined {
  if (!date) return undefined;
  return endOfDay ? `${date}T23:59:59.999Z` : `${date}T00:00:00.000Z`;
}
