"use client";

import { useEffect, useId, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  searchUsersRequest,
  type UserSearchHit,
} from "@/lib/api";

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 300;

interface UserSearchPickerProps {
  selected: UserSearchHit | null;
  onSelect: (user: UserSearchHit | null) => void;
  disabled?: boolean;
  /** Extra user ids to omit (document owner). Caller is always excluded by the API. */
  excludeUserIds?: string[];
}

/**
 * Searchable recipient picker backed by GET /users/search.
 * Keeps the internal user id in state — the owner never types a UUID by hand.
 */
export function UserSearchPicker({
  selected,
  onSelect,
  disabled = false,
  excludeUserIds = [],
}: UserSearchPickerProps) {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const listId = useId();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSearchHit[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  const excludeKey = excludeUserIds.filter(Boolean).sort().join(",");

  useEffect(() => {
    if (!accessToken || disabled) return;
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([]);
      setStatus("idle");
      setError(null);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void (async () => {
        setStatus("loading");
        setError(null);
        try {
          const data = await searchUsersRequest(
            accessToken,
            {
              q: trimmed,
              page_size: 10,
              exclude_user_id: excludeUserIds.filter(Boolean),
            },
            controller.signal,
          );
          setResults(data.results);
          setStatus("ready");
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") return;
          if (handleUnauthorized(err)) return;
          setResults([]);
          setError(
            err instanceof ApiError ? err.detail : "User search failed.",
          );
          setStatus("error");
        }
      })();
    }, DEBOUNCE_MS);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
    // excludeKey tracks excludeUserIds without depending on array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- excludeKey is the stable fingerprint
  }, [accessToken, disabled, excludeKey, handleUnauthorized, query]);

  if (selected) {
    return (
      <div className="rounded-md border border-border bg-white px-3 py-2 text-sm">
        <p className="font-medium text-foreground">{selected.name}</p>
        <p className="text-xs text-muted">{selected.email}</p>
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            onSelect(null);
            setQuery("");
            setResults([]);
            setStatus("idle");
          }}
          className="mt-2 text-xs font-semibold text-accent-strong hover:underline disabled:opacity-60"
        >
          Change recipient
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Find recipient</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Name, email, or user ID"
          autoComplete="off"
          disabled={disabled}
          aria-controls={listId}
          aria-expanded={status === "ready" && results.length > 0}
          className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-60"
        />
      </label>
      <p className="text-xs text-muted">
        Search registered users by name or email. You cannot grant access to
        yourself or the document owner.
      </p>

      {query.trim().length > 0 && query.trim().length < MIN_QUERY_LENGTH ? (
        <p className="text-xs text-muted">
          Type at least {MIN_QUERY_LENGTH} characters.
        </p>
      ) : null}

      {status === "loading" ? (
        <p className="text-xs text-muted" role="status">
          Searching…
        </p>
      ) : null}

      {status === "error" && error ? (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : null}

      {status === "ready" && results.length === 0 ? (
        <p className="text-xs text-muted">
          No matching active users. Try another name or email.
        </p>
      ) : null}

      {status === "ready" && results.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Matching users"
          className="max-h-48 overflow-y-auto rounded-md border border-border bg-white"
        >
          {results.map((hit) => (
            <li key={hit.id} role="option">
              <button
                type="button"
                disabled={disabled}
                onClick={() => {
                  onSelect(hit);
                  setQuery("");
                  setResults([]);
                  setStatus("idle");
                }}
                className="flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-accent-soft disabled:opacity-60"
              >
                <span className="font-medium text-foreground">{hit.name}</span>
                <span className="text-xs text-muted">{hit.email}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
