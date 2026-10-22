"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, toApiError, toApiProfile } from "@/lib/api";

/**
 * Run an async fetcher({signal}) whenever `deps` change. Returns {status, data, error, reload}.
 * status: "idle" (disabled) | "loading" | "success" | "error". In-flight requests are cancelled on change/unmount.
 */
export function useApiQuery(fetcher, deps, { enabled = true } = {}) {
  const [state, setState] = useState({ status: enabled ? "loading" : "idle", data: null, error: null });
  const [version, setVersion] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle", data: null, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    fetcherRef.current(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ status: "success", data, error: null });
      },
      (error) => {
        if (!controller.signal.aborted) setState({ status: "error", data: null, error: toApiError(error) });
      },
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version, enabled]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { ...state, reload };
}

/**
 * Paginated scholarship search with "Load more": page 1 reloads whenever `params` change; further pages append.
 * `params` is a plain object of API query parameters (blank values are ignored by the client).
 */
export function useScholarshipSearch(params, pageSize = 12) {
  const key = JSON.stringify(params);
  const first = useApiQuery(
    (signal) => api.listScholarships({ ...params, page: 1, page_size: pageSize }, { signal }),
    [key, pageSize],
  );
  const [more, setMore] = useState({ pages: [], loading: false, error: null });

  useEffect(() => {
    setMore({ pages: [], loading: false, error: null });
  }, [key, first.status === "loading"]); // reset appended pages whenever page 1 is (re)loaded

  const items = useMemo(
    () => (first.data ? [...first.data.items, ...more.pages.flatMap((p) => p.items)] : []),
    [first.data, more.pages],
  );
  const total = first.data ? first.data.total : 0;
  const hasMore = first.status === "success" && items.length < total;

  const loadMore = useCallback(async () => {
    if (more.loading) return;
    setMore((m) => ({ ...m, loading: true, error: null }));
    try {
      const nextPage = 2 + more.pages.length;
      const page = await api.listScholarships({ ...params, page: nextPage, page_size: pageSize });
      setMore((m) => ({ pages: [...m.pages, page], loading: false, error: null }));
    } catch (error) {
      setMore((m) => ({ ...m, loading: false, error: toApiError(error) }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, pageSize, more.loading, more.pages.length]);

  return {
    status: first.status,
    error: first.error,
    reload: first.reload,
    items,
    total,
    hasMore,
    loadMore,
    loadingMore: more.loading,
    loadMoreError: more.error,
  };
}

/**
 * Eligibility results for the given ids, as a map id -> result. Failure is non-fatal for callers.
 * `profile` is the UI profile (form fields); it is converted to the API's shape exactly once, inside api.checkEligibility.
 */
export function useEligibility(profile, ids) {
  const key = JSON.stringify([toApiProfile(profile), ids]); // re-check only when an eligibility-relevant field changes
  const query = useApiQuery((signal) => api.checkEligibility(profile, ids, { signal }), [key], { enabled: ids.length > 0 });
  const byId = useMemo(() => {
    const map = {};
    for (const result of query.data?.results ?? []) map[result.scholarship_id] = result;
    return map;
  }, [query.data]);
  return { byId, status: query.status, error: query.error, reload: query.reload };
}
