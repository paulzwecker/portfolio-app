"use client";

import { useState } from "react";
import { CloudDownload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  isGoogleSheetsAgentWorkPublish,
  type GoogleSheetsAgentWorkPublish,
} from "@/lib/domain-contracts";

const roles = [
  ["DATA_UNIVERSE_STEWARD", "Data & Universe Steward"],
  ["PORTFOLIO_THESIS_SENTINEL", "Portfolio & Thesis Sentinel"],
  ["MODEL_ALLOCATION_STEWARD", "Model & Allocation Steward"],
] as const;

export function GoogleSheetsAgentWorkFeed({
  portfolioId,
}: {
  portfolioId?: string;
}) {
  const [role, setRole] = useState<(typeof roles)[number][0]>(roles[0][0]);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<GoogleSheetsAgentWorkPublish | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function publish() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(
        `/api/research/google-sheets-agent-operations/${role}/work/publish`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            limit: 10,
            offset,
            portfolio_id: portfolioId ?? null,
          }),
          cache: "no-store",
        },
      );
      const payload: unknown = await response.json();
      if (!response.ok) {
        const detail =
          typeof payload === "object" && payload !== null && "detail" in payload
            ? String(payload.detail)
            : "The agent work publication failed.";
        throw new Error(detail);
      }
      if (!isGoogleSheetsAgentWorkPublish(payload))
        throw new Error(
          "The API response did not match the work-feed contract.",
        );
      setResult(payload);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The agent work publication failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Publish agent work feed</CardTitle>
        <CardDescription>
          Manually deliver up to ten bounded work items to the application-owned
          Sheets tab. The delivery is recorded only after the write passes
          read-back verification.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="grid flex-1 gap-1 text-sm font-medium">
            Existing automation
            <select
              className="h-10 rounded-md border bg-background px-3 text-sm"
              value={role}
              onChange={(event) => setRole(event.target.value as typeof role)}
              aria-label="Research agent role"
            >
              {roles.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-medium">
            Page offset
            <input
              className="h-10 w-full rounded-md border bg-background px-3 text-sm sm:w-32"
              type="number"
              min={0}
              max={5000}
              step={10}
              value={offset}
              onChange={(event) =>
                setOffset(
                  Math.max(0, Math.min(5000, Number(event.target.value) || 0)),
                )
              }
              aria-label="Agent work page offset"
            />
          </label>
          <Button disabled={busy} onClick={() => void publish()}>
            <CloudDownload aria-hidden="true" />
            {busy ? "Publishing…" : "Publish work"}
          </Button>
        </div>
        {error && (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 p-3 text-sm"
          >
            {error}
          </p>
        )}
        {result && (
          <div
            className="rounded-md border bg-muted/30 p-3 text-sm"
            role="status"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant={
                  result.status === "BLOCKED" ? "destructive" : "secondary"
                }
              >
                {result.status}
              </Badge>
              <span>{result.message}</span>
            </div>
            <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-muted-foreground">Items in page</dt>
                <dd className="mt-1">{result.work_item_count}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Page begins at item</dt>
                <dd className="mt-1">{offset + 1}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">New rows</dt>
                <dd className="mt-1">{result.added_count}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Feed rows</dt>
                <dd className="mt-1">{result.row_count}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Read-back</dt>
                <dd className="mt-1">
                  {result.read_back_verified ? "Verified" : "Not verified"}
                </dd>
              </div>
            </dl>
            {result.status_reason && (
              <p className="mt-3 text-xs text-muted-foreground">
                {result.status_reason}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
