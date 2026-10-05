"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DemoNotice,
  PageTitle,
  PendingOrError,
  useResearch,
} from "@/components/research-frame";
import { isOverview, isPortfolios } from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";

export default function PortfolioPage() {
  const state = useResearch("portfolios", isPortfolios);
  if (!state.data)
    return (
      <>
        <PageTitle
          title="Portfolio"
          description="Observed holdings and the architecture you want to own."
        />
        <PendingOrError {...state} />
      </>
    );
  if (state.data.length === 0)
    return (
      <>
        <PageTitle
          title="Portfolio"
          description="Observed holdings and strategic targets remain separate."
        />
        <Card>
          <CardContent className="py-10">
            <h2 className="text-lg font-medium">No portfolio yet</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Create your logical portfolio through the API, or run the
              documented development seed to explore fictional examples.
            </p>
          </CardContent>
        </Card>
      </>
    );
  return <PortfolioView id={state.data[0].id} />;
}

function money(value: string | null, currency: string | null) {
  if (value === null) return "Unavailable";
  if (!currency) return quantity(value);
  try {
    return new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(Number(value));
  } catch {
    return `${quantity(value)} ${currency}`;
  }
}

function PortfolioView({ id }: { id: string }) {
  const state = useResearch(`portfolios/${id}/overview`, isOverview);
  const view = state.data;
  if (!view)
    return (
      <>
        <PageTitle
          title="Portfolio"
          description="Observed holdings and the architecture you want to own."
        />
        <PendingOrError {...state} />
      </>
    );
  return (
    <>
      <PageTitle
        title="Portfolio"
        description={view.portfolio.name}
        demo={view.portfolio.is_demo}
      />
      {view.portfolio.is_demo && <DemoNotice />}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Holdings observation</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant="outline">
              {view.snapshot?.completeness ?? "Not observed"}
            </Badge>
            <p className="mt-3 text-xs text-muted-foreground">
              {view.snapshot
                ? date(view.snapshot.effective_at)
                : "No holdings snapshot has been recorded."}
            </p>
            {view.snapshot?.completeness === "PARTIAL" && (
              <p className="mt-3 text-xs leading-5 text-amber-800 dark:text-amber-300">
                {view.snapshot.reason}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Invested strategic target</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {view.target_revision
                ? percent(view.target_revision.invested_weight)
                : "Not authored"}
            </p>
            <p className="mt-3 text-xs text-muted-foreground">
              {view.target_revision
                ? `Accepted ${date(view.target_revision.accepted_at!)}`
                : "No accepted target revision."}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Strategic cash target</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {view.target_revision
                ? percent(view.target_revision.strategic_cash_weight)
                : "Not authored"}
            </p>
            <p className="mt-3 text-xs text-muted-foreground">
              Residual of the accepted company targets.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Current market value</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">
              {money(view.base_market_value, view.valuation_currency)}
            </p>
            <p className="mt-3 text-xs text-muted-foreground">
              {view.valuation_status.replaceAll("_", " ")}
            </p>
          </CardContent>
        </Card>
      </div>
      <div className="mb-6 rounded-lg border bg-secondary/40 p-4 text-sm leading-6">
        <p>
          Native-currency market values use fresh listing-specific daily closes.
          Portfolio weights and allocation gaps appear only when every holding
          and cash balance has comparable dated prices and FX.
        </p>
        {view.valuation_gaps.length > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            Unresolved coverage:{" "}
            {view.valuation_gaps
              .map(
                (gap) => `${gap.identity} (${gap.reason.replaceAll("_", " ")})`,
              )
              .join(" · ")}
          </p>
        )}
      </div>
      <Card>
        <CardHeader className="border-b">
          <CardTitle>Businesses and target architecture</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {view.companies.length === 0 && (
            <p className="p-6 text-sm text-muted-foreground">
              {view.snapshot?.completeness === "COMPLETE"
                ? "The complete snapshot contains no security positions or authored company targets."
                : "Holdings or targets have not been observed."}
            </p>
          )}
          {view.companies.map((row) => (
            <article
              key={row.company.id}
              className="grid gap-4 border-b p-5 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_180px]"
            >
              <div>
                <Link
                  href={`/company/${row.company.id}`}
                  className="inline-flex items-center gap-2 font-medium hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {row.company.name}
                  <ArrowUpRight aria-hidden="true" className="size-4" />
                </Link>
                <p className="mt-1 text-xs text-muted-foreground">
                  {row.company.lifecycle ?? "Lifecycle unassigned"}
                </p>
                <ul className="mt-3 space-y-2 text-sm">
                  {row.positions.map((p) => (
                    <li key={p.listing_id}>
                      <span className="font-medium">{p.ticker}</span>{" "}
                      <span className="text-muted-foreground">
                        · {p.venue} · {p.currency ?? "Currency unknown"}
                      </span>
                      <p className="text-xs text-muted-foreground">
                        {p.security_name}: {quantity(p.quantity)} shares
                        {p.latest_price &&
                          ` · ${money(p.latest_price, p.price_currency)} as of ${p.price_date ? new Date(p.price_date).toLocaleDateString() : "unknown date"}`}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Current value:{" "}
                        {money(p.native_market_value, p.price_currency)}
                        {p.valuation_status === "VALUED" &&
                        p.price_currency !== view.valuation_currency
                          ? ` · ${money(p.base_market_value, view.valuation_currency)} base`
                          : p.valuation_status !== "VALUED"
                            ? ` · ${p.valuation_status.replaceAll("_", " ")}`
                            : ""}
                      </p>
                    </li>
                  ))}
                </ul>
                {row.positions.length === 0 && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    {view.snapshot?.completeness === "COMPLETE"
                      ? "No position in the complete snapshot."
                      : "No position observed; holdings may be incomplete."}
                  </p>
                )}
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm sm:block sm:space-y-2">
                <dt className="text-xs text-muted-foreground">
                  Company target
                </dt>
                <dd className="font-semibold">{percent(row.target_weight)}</dd>
                <dt className="text-xs text-muted-foreground">
                  Current value / weight / gap
                </dt>
                <dd className="font-medium tabular-nums">
                  {row.current_market_value === null
                    ? row.allocation_status.replaceAll("_", " ")
                    : `${money(row.current_market_value, row.current_market_currency)} · ${percent(row.current_weight)} · gap ${row.allocation_gap === null ? "Unavailable" : percent(row.allocation_gap)}`}
                </dd>
              </dl>
            </article>
          ))}
          {view.standalone_positions.length > 0 && (
            <section
              className="border-t p-5"
              aria-labelledby="standalone-holdings"
            >
              <h3 id="standalone-holdings" className="font-medium">
                Standalone securities
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                These instruments are held in the portfolio without representing
                a company in the research universe.
              </p>
              <ul className="mt-3 space-y-3 text-sm">
                {view.standalone_positions.map((position) => (
                  <li key={position.listing_id}>
                    <span className="font-medium">
                      {position.security_name}
                    </span>
                    <span className="text-muted-foreground">
                      {` · ${position.ticker} · ${position.venue} · ${position.currency ?? "Currency unknown"}`}
                    </span>
                    <p className="text-xs text-muted-foreground">
                      {quantity(position.quantity)} shares
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Current value:{" "}
                      {money(
                        position.native_market_value,
                        position.price_currency,
                      )}
                      {position.valuation_status !== "VALUED" &&
                        ` · ${position.valuation_status.replaceAll("_", " ")}`}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </CardContent>
      </Card>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Native-currency cash</CardTitle>
        </CardHeader>
        <CardContent>
          {!view.snapshot || view.snapshot.completeness !== "COMPLETE" ? (
            <p className="mb-3 text-sm text-muted-foreground">
              Cash observations may be missing or incomplete.
            </p>
          ) : null}
          {view.snapshot?.cash_positions.length ? (
            <div className="flex flex-wrap gap-5">
              {view.snapshot.cash_positions.map((cash) => (
                <dl key={cash.currency}>
                  <dt className="text-xs text-muted-foreground">
                    {cash.currency}
                  </dt>
                  <dd className="mt-1 font-medium">{quantity(cash.balance)}</dd>
                </dl>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No cash balances recorded.
            </p>
          )}
          <p className="mt-4 text-xs text-muted-foreground">
            Balances retain their original currency. A base-currency cash value
            is used only with a valid dated FX observation.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
