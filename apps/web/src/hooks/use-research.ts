"use client";

import { useEffect, useState } from "react";

export function useResearch<T>(
  path: string,
  validate: (data: unknown) => data is T,
  refreshIntervalMs = 0,
  enabled = true,
) {
  const [state, setState] = useState<{
    path: string;
    data?: T;
    error?: string;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
      setState({
        path,
        error: "The request timed out. Check the services and retry.",
      });
    }, 10_000);

    fetch(`/api/research/${path}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        const data: unknown = await response.json();
        if (!response.ok)
          throw new Error(
            response.status === 404
              ? "This record was not found."
              : "Research data is unavailable. Check the API, database and migrations, then retry.",
          );
        if (!validate(data))
          throw new Error(
            "Research data could not be verified. Retry after checking the API.",
          );
        if (!controller.signal.aborted) setState({ path, data });
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted)
          setState({
            path,
            error:
              failure instanceof Error &&
              failure.message === "This record was not found."
                ? failure.message
                : "Research data is unavailable. Check the API, database and migrations, then retry.",
          });
      })
      .finally(() => clearTimeout(timer));

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [path, validate, attempt, enabled]);

  useEffect(() => {
    if (refreshIntervalMs <= 0) return;
    const interval = setInterval(
      () => setAttempt((current) => current + 1),
      refreshIntervalMs,
    );
    return () => clearInterval(interval);
  }, [refreshIntervalMs]);

  useEffect(() => {
    const refreshAfterManualOperation = () =>
      setAttempt((current) => current + 1);
    window.addEventListener(
      "portfolio:data-refreshed",
      refreshAfterManualOperation,
    );
    return () =>
      window.removeEventListener(
        "portfolio:data-refreshed",
        refreshAfterManualOperation,
      );
  }, []);

  const current = state?.path === path ? state : null;
  return {
    data: enabled ? current?.data : undefined,
    error: enabled ? current?.error : undefined,
    retry: () => {
      setState(null);
      setAttempt((currentAttempt) => currentAttempt + 1);
    },
  };
}
