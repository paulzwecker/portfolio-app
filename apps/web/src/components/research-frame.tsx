"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function useResearch<T>(
  path: string,
  validate: (data: unknown) => data is T,
) {
  const [state, setState] = useState<{
    path: string;
    data?: T;
    error?: string;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
      setState({
        path,
        error: "The request timed out. Check the services and retry.",
      });
    }, 10000);
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
  }, [path, validate, attempt]);
  const current = state?.path === path ? state : null;
  return {
    data: current?.data,
    error: current?.error,
    retry: () => {
      setState(null);
      setAttempt((n) => n + 1);
    },
  };
}

export function PendingOrError({
  error,
  retry,
}: {
  error?: string;
  retry: () => void;
}) {
  return error ? (
    <div role="alert" className="rounded-xl border bg-card p-6">
      <p>{error}</p>
      <Button className="mt-4" variant="outline" onClick={retry}>
        <RefreshCw aria-hidden="true" />
        Retry
      </Button>
    </div>
  ) : (
    <p
      role="status"
      className="flex items-center gap-2 py-8 text-sm text-muted-foreground"
    >
      <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
      Loading research data
    </p>
  );
}

export function PageTitle({
  title,
  description,
  demo,
}: {
  title: string;
  description: string;
  demo?: boolean;
}) {
  return (
    <div className="mb-7">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        {demo && <Badge variant="secondary">Demo data</Badge>}
      </div>
      <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
        {description}
      </p>
    </div>
  );
}

export function DemoNotice() {
  return (
    <p className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
      Fictional demonstration data. This workspace has not been migrated from
      the legacy workbook.
    </p>
  );
}
