"use client";

import { Search, UserRound, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
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
  const inputId = useId();

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
      <div className="flex items-start gap-3 rounded-[0.75rem] border border-border bg-accent-soft/40 px-3 py-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface text-accent-strong shadow-[var(--shadow-sm)]">
          <UserRound className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">
            {selected.name}
          </p>
          <p className="truncate text-xs text-muted">{selected.email}</p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={() => {
            onSelect(null);
            setQuery("");
            setResults([]);
            setStatus("idle");
          }}
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          Change
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="tv-label">
        Find recipient
      </label>
      <div className="relative">
        <span className="tv-input-icon-slot tv-input-icon-slot--leading" aria-hidden>
          <Search className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <input
          id={inputId}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Name or email"
          autoComplete="off"
          disabled={disabled}
          aria-controls={listId}
          aria-expanded={status === "ready" && results.length > 0}
          className="tv-input tv-input-with-leading-icon disabled:opacity-60"
        />
      </div>
      <p className="text-xs text-muted">
        Search registered users. You cannot grant access to yourself or the
        document owner.
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
          className="max-h-48 overflow-y-auto rounded-[0.75rem] border border-border bg-surface shadow-[var(--shadow-sm)]"
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
                className="flex w-full flex-col items-start px-3 py-2.5 text-left text-sm transition-colors duration-[160ms] hover:bg-accent-soft disabled:opacity-60"
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
