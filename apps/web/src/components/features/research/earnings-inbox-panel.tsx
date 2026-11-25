"use client";
import Link from "next/link";
import { useState } from "react";
import { PendingOrError } from "@/components/app/empty-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import { isPortfolios } from "@/lib/domain-contracts";
import { isEarningsInbox } from "@/lib/earnings-inbox";

export function EarningsInboxPanel() {
  const portfolios = useResearch("portfolios", isPortfolios);
  const [selected, setSelected] = useState("");
  const id = selected || portfolios.data?.[0]?.id || "";
  const inbox = useResearch(
    `portfolios/${id}/earnings-inbox`,
    isEarningsInbox,
    0,
    Boolean(id),
  );
  if (!portfolios.data)
    return <PendingOrError error={portfolios.error} retry={portfolios.retry} />;
  if (!portfolios.data.length) return <p>No portfolio available.</p>;
  const data = inbox.data;
  return (
    <section aria-label="Portfolio earnings inbox" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Earnings inbox</h2>
        {portfolios.data.length > 1 && (
          <select
            aria-label="Portfolio"
            value={id}
            onChange={(e) => setSelected(e.target.value)}
          >
            {portfolios.data.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
      </div>
      {!data ? (
        <PendingOrError error={inbox.error} retry={inbox.retry} />
      ) : !data.snapshot_id ? (
        <p>No complete holdings snapshot is available.</p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {data.listing_count} held listings · {data.modeled_count} with an
            accepted DCF · Snapshot {data.effective_at?.slice(0, 10)}
          </p>
          {!data.listing_count && <p>No positive holdings in this snapshot.</p>}
          {data.rows
            .filter((r) => r.url)
            .map((r, i) => (
              <Card key={[r.listing_id, r.url, r.proposal_id, i].join("/")}>
                <CardContent className="space-y-3 py-4">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <h3 className="font-semibold">{r.company}</h3>
                    <span className="text-sm text-muted-foreground">
                      {r.listing}
                    </span>
                    <Badge variant="outline">
                      {r.outcome.replaceAll("_", " ")}
                    </Badge>
                  </div>
                  <p>
                    <a
                      className="underline"
                      href={r.url!}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {r.title}
                    </a>{" "}
                    {r.period} {r.published_at}
                  </p>
                  {r.passage && (
                    <blockquote className="border-l-2 pl-3 text-sm">
                      {r.passage}
                    </blockquote>
                  )}
                  {r.comparison && <p>{r.comparison}</p>}
                  {r.rationale && <p className="text-sm">{r.rationale}</p>}
                  {r.impact_bps != null ? (
                    <p className="font-medium">
                      Enterprise IRR {(Number(r.irr_before) * 100).toFixed(2)}%
                      → {(Number(r.irr_after) * 100).toFixed(2)}% (
                      {Number(r.impact_bps).toFixed(2)} bp)
                      {r.crosses_hurdle && " · Crosses 15% hurdle"}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {r.revision_number == null
                        ? "No accepted DCF for this listing"
                        : r.proposal_id
                          ? `Comparable IRR unavailable · ${r.price_status ?? "Preview required"}`
                          : r.outcome === "RETAIN"
                            ? "Accepted assumption retained"
                            : "No valuation comparison recorded"}
                    </p>
                  )}
                  {r.decision_note && (
                    <p className="text-sm">Reviewer note · {r.decision_note}</p>
                  )}
                  <Link
                    className="text-sm underline"
                    href={`/company/${r.company_id}?view=valuation&listing=${r.listing_id}${r.proposal_id ? `&proposal=${r.proposal_id}#model-proposals-title` : ""}`}
                  >
                    {r.proposal_id ? "Open proposal" : "Open valuation"}
                  </Link>
                </CardContent>
              </Card>
            ))}
          {data.rows.some((r) => !r.url) && (
            <details className="rounded-md border p-3">
              <summary>
                Holdings without a recorded earnings publication (
                {data.rows.filter((r) => !r.url).length})
              </summary>
              <ul className="mt-2 divide-y">
                {data.rows
                  .filter((r) => !r.url)
                  .map((r) => (
                    <li
                      className="flex flex-wrap justify-between gap-2 py-2 text-sm"
                      key={r.listing_id}
                    >
                      {r.company_id ? (
                        <Link
                          href={`/company/${r.company_id}?view=valuation&listing=${r.listing_id}`}
                        >
                          {r.company} · {r.listing}
                        </Link>
                      ) : (
                        <span>{r.listing}</span>
                      )}
                      <span>
                        {r.revision_number
                          ? `DCF revision ${r.revision_number}`
                          : "No accepted DCF"}
                      </span>
                    </li>
                  ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
