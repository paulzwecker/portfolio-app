"use client";

import { useEffect, useState } from "react";
import { Check, Circle, LoaderCircle, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchHealth, type HealthResponse } from "@/lib/health";
import { cn } from "@/lib/utils";

type ConnectionState =
  | { kind: "checking" }
  | { kind: "received"; health: HealthResponse }
  | { kind: "unavailable" };

export function ServiceStatus() {
  const [state, setState] = useState<ConnectionState>({ kind: "checking" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8_000);
    let active = true;
    fetchHealth(controller.signal)
      .then((health) => {
        if (active) setState({ kind: "received", health });
      })
      .catch(() => {
        if (active) setState({ kind: "unavailable" });
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  const checking = state.kind === "checking";
  const health = state.kind === "received" ? state.health : null;
  const ready = health?.status === "ok";
  const summary = checking
    ? "Checking connection"
    : ready
      ? "All services connected"
      : "Connection needs attention";

  return (
    <Card className="shadow-none">
      <CardHeader className="gap-3 pb-5">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Connection</CardTitle>
          <Badge
            variant="outline"
            className="font-normal text-muted-foreground"
          >
            Development
          </Badge>
        </div>
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="flex gap-2 text-sm"
        >
          {checking ? (
            <LoaderCircle
              aria-hidden="true"
              className="mt-0.5 size-4 animate-spin motion-reduce:animate-none"
            />
          ) : (
            <span
              className={cn(
                "mt-1.5 size-2 shrink-0 rounded-full",
                ready ? "bg-primary" : "bg-amber-600",
              )}
            />
          )}
          <span>{summary}</span>
        </div>
      </CardHeader>
      <CardContent>
        <dl className="space-y-4 border-t pt-5 text-sm">
          <StatusRow label="Application" value="Connected" connected />
          <StatusRow
            label="API"
            value={checking ? "Checking" : health ? "Connected" : "Unavailable"}
            connected={health !== null}
          />
          <StatusRow
            label="Database"
            value={
              checking
                ? "Checking"
                : health?.database === "connected"
                  ? "Connected"
                  : "Unavailable"
            }
            connected={health?.database === "connected"}
          />
          <StatusRow
            label="Schema"
            value={
              checking
                ? "Checking"
                : health?.schema === "current"
                  ? "Current"
                  : health?.schema === "outdated"
                    ? "Migration required"
                    : "Unavailable"
            }
            connected={health?.schema === "current"}
          />
        </dl>
        {!checking && !ready && (
          <p className="mt-5 rounded-md bg-amber-50 p-3 text-xs leading-relaxed text-amber-950">
            {health?.schema === "outdated"
              ? "The database is reachable. Apply the documented database migrations, then retry."
              : "Check that the API and PostgreSQL are running and the environment is configured, then retry."}
          </p>
        )}
        <div className="mt-6 flex items-center justify-between gap-2 border-t pt-4">
          <p className="text-xs text-muted-foreground">
            {health ? (
              <>
                Checked{" "}
                <time
                  dateTime={health.checked_at}
                  title={new Date(health.checked_at).toLocaleString()}
                >
                  {new Date(health.checked_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </time>
              </>
            ) : (
              "Live service check"
            )}
          </p>
          <Button
            variant="ghost"
            size="sm"
            disabled={checking}
            onClick={() => {
              setState({ kind: "checking" });
              setAttempt((value) => value + 1);
            }}
          >
            <RefreshCw aria-hidden="true" />
            {checking ? "Checking" : "Retry"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusRow({
  label,
  value,
  connected,
}: {
  label: string;
  value: string;
  connected: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="flex items-center gap-1.5 text-right text-xs font-medium">
        {connected ? (
          <Check aria-hidden="true" className="size-3.5 text-primary" />
        ) : (
          <Circle aria-hidden="true" className="size-2 text-muted-foreground" />
        )}
        {value}
      </dd>
    </div>
  );
}
