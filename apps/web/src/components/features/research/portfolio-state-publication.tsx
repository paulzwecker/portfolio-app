"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  isGoogleSheetsPortfolioStatePublish,
  isPortfolios,
} from "@/lib/domain-contracts";
import { useResearch } from "@/hooks/use-research";
import { dateTime } from "@/lib/display";

export function PortfolioStatePublication() {
  const portfolios = useResearch("portfolios", isPortfolios);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{
    status: string;
    message: string;
    valuationAsOf: string | null;
    valuationStatus: string;
    fingerprint: string;
    rowCount: number;
  } | null>(null);
  const portfolioId = portfolios.data?.some((item) => item.id === selectedId)
    ? selectedId
    : (portfolios.data?.[0]?.id ?? "");

  async function publish() {
    if (!portfolioId) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch(
        "/api/research/google-sheets-sync/portfolio-state/publish",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ portfolio_id: portfolioId }),
          cache: "no-store",
        },
      );
      const payload: unknown = await response.json();
      if (!response.ok || !isGoogleSheetsPortfolioStatePublish(payload)) {
        const detail =
          typeof payload === "object" && payload !== null && "detail" in payload
            ? String(payload.detail)
            : "Canonical portfolio state could not be published.";
        throw new Error(detail);
      }
      setResult({
        status: payload.status,
        message: payload.message,
        valuationAsOf: payload.valuation_as_of,
        valuationStatus: payload.valuation_status,
        fingerprint: payload.content_fingerprint,
        rowCount: payload.row_count,
      });
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Canonical portfolio state could not be published.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Publish canonical portfolio state</CardTitle>
        <CardDescription>
          Manually publish the selected portfolio snapshot and current valuation
          context to the application-owned Sheets tab. This is a read-only
          handoff; Sheets cannot change holdings or targets.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {portfolios.error ? (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 p-3 text-sm"
          >
            Portfolio list unavailable. Retry before publishing state.
          </p>
        ) : !portfolios.data?.length ? (
          <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            No canonical portfolio is available to publish.
          </p>
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="grid min-w-0 flex-1 gap-1 text-sm font-medium">
              Portfolio
              <select
                aria-label="Portfolio state portfolio"
                value={portfolioId}
                onChange={(event) => setSelectedId(event.target.value)}
                className="h-10 rounded-md border bg-background px-3 text-sm"
              >
                {portfolios.data.map((portfolio) => (
                  <option key={portfolio.id} value={portfolio.id}>
                    {portfolio.name} · {portfolio.base_currency}
                  </option>
                ))}
              </select>
            </label>
            <Button
              disabled={busy || !portfolioId}
              onClick={() => void publish()}
            >
              {busy ? "Publishing…" : "Publish current state"}
            </Button>
          </div>
        )}
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
            role="status"
            className="rounded-md border bg-muted/30 p-3 text-sm"
          >
            <p className="font-medium">
              {result.status} · {result.message}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Valuation {result.valuationStatus} · as of{" "}
              {dateTime(result.valuationAsOf)} · {result.rowCount} rows ·{" "}
              {result.fingerprint}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
