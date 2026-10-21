"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth, useHandleUnauthorized } from "@/components/auth-provider";
import {
  ApiError,
  listDocumentsRequest,
  type DocumentListItem,
  type DocumentListParams,
  type DocumentListResponse,
} from "@/lib/api";

export type ListStatus = "idle" | "loading" | "ready" | "error" | "empty";

export interface UseDocumentListResult {
  status: ListStatus;
  results: DocumentListItem[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  errorMessage: string | null;
  refresh: () => void;
  setPage: (page: number) => void;
}

function filtersKey(params: DocumentListParams): string {
  return JSON.stringify({
    title: params.title ?? "",
    owner_id: params.owner_id ?? "",
    owner_email: params.owner_email ?? "",
    category: params.category ?? "",
    created_from: params.created_from ?? "",
    created_to: params.created_to ?? "",
    page_size: params.page_size ?? 20,
  });
}

export function useDocumentList(
  params: DocumentListParams,
  options?: { enabled?: boolean },
): UseDocumentListResult {
  const { accessToken } = useAuth();
  const handleUnauthorized = useHandleUnauthorized();
  const enabled = options?.enabled ?? true;

  const [fetchStatus, setFetchStatus] = useState<ListStatus>("idle");
  const [payload, setPayload] = useState<DocumentListResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [page, setPageState] = useState(1);
  const [reloadTick, setReloadTick] = useState(0);
  const requestIdRef = useRef(0);

  const key = filtersKey(params);
  const [activeFilterKey, setActiveFilterKey] = useState(key);
  if (key !== activeFilterKey) {
    setActiveFilterKey(key);
    setPageState(1);
  }
  const effectivePage = key === activeFilterKey ? page : 1;

  const sessionReady = Boolean(enabled && accessToken);
  const status: ListStatus = sessionReady ? fetchStatus : "idle";

  useEffect(() => {
    if (!enabled || !accessToken) return;

    const requestId = ++requestIdRef.current;
    const controller = new AbortController();
    const token = accessToken;
    const query: DocumentListParams = {
      title: params.title,
      owner_id: params.owner_id,
      owner_email: params.owner_email,
      category: params.category,
      created_from: params.created_from,
      created_to: params.created_to,
      page: effectivePage,
      page_size: params.page_size ?? 20,
    };

    void (async () => {
      setFetchStatus("loading");
      setErrorMessage(null);
      try {
        const data = await listDocumentsRequest(token, query, controller.signal);
        if (requestId !== requestIdRef.current) return;
        setPayload(data);
        setFetchStatus(data.results.length === 0 ? "empty" : "ready");
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (requestId !== requestIdRef.current) return;
        if (handleUnauthorized(error)) return;
        const message =
          error instanceof ApiError
            ? error.detail
            : "Unable to load documents.";
        setPayload(null);
        setErrorMessage(message);
        setFetchStatus("error");
      }
    })();

    return () => {
      controller.abort();
    };
  }, [
    accessToken,
    enabled,
    handleUnauthorized,
    key,
    effectivePage,
    reloadTick,
    params.title,
    params.owner_id,
    params.owner_email,
    params.category,
    params.created_from,
    params.created_to,
    params.page_size,
  ]);

  const refresh = useCallback(() => {
    setReloadTick((value) => value + 1);
  }, []);

  const setPage = useCallback((next: number) => {
    setPageState(Math.max(1, next));
  }, []);

  return {
    status,
    results: sessionReady ? (payload?.results ?? []) : [],
    page: payload?.page ?? effectivePage,
    pageSize: payload?.page_size ?? params.page_size ?? 20,
    total: sessionReady ? (payload?.total ?? 0) : 0,
    totalPages: sessionReady ? (payload?.total_pages ?? 0) : 0,
    errorMessage: sessionReady ? errorMessage : null,
    refresh,
    setPage,
  };
}
