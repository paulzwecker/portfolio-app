import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { portfolioFixture } from "../../../../e2e/fixtures/portfolio";
import { portfolioHoldingRows } from "./portfolio-data";
import { PortfolioHoldingsSection } from "./portfolio-holdings-section";
import { PortfolioOverviewSection } from "./portfolio-overview-section";

describe("Portfolio valuation evidence", () => {
  it("labels listing disclosures and company-level targets", () => {
    const overview = portfolioFixture();
    const html = renderToStaticMarkup(
      <PortfolioHoldingsSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
        onConfirmed={() => {}}
      />,
    );
    expect(html).toContain('aria-label="FX details for T02 NASDAQ"');
    expect(html).toContain("Listing weight");
    expect(html).toContain("Company target / gap");
    expect(html).toContain("FX effective and quote observation times differ");
    expect(html).not.toContain("non-synchronous close");
  });
  it("renders each listing weight separately when a company has multiple listings", () => {
    const overview = portfolioFixture();
    const first = overview.companies[0];
    const second = overview.companies[1];
    first.current_weight = "0.10";
    first.positions[0].portfolio_weight = "0.07";
    second.positions[0].portfolio_weight = "0.03";
    first.positions.push(second.positions[0]);
    overview.companies.splice(1, 1);
    const html = renderToStaticMarkup(
      <PortfolioHoldingsSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
        onConfirmed={() => {}}
      />,
    );
    const rows = html.match(/<tr class="align-top">.*?<\/tr>/g) ?? [];
    const firstRow = rows.find((row) => row.includes("T01"));
    const secondRow = rows.find((row) => row.includes("T02"));
    expect(firstRow).toContain("7%");
    expect(secondRow).toContain("3%");
    expect(firstRow).not.toContain("10%");
    expect(secondRow).not.toContain("10%");
  });
  it("labels effective and market-session dates without calling them observation times", () => {
    const overview = portfolioFixture();
    overview.valuation_status = "INCOMPLETE_PRICE_COVERAGE";
    const html = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
      />,
    );
    expect(html).toContain("Holdings snapshot");
    expect(html).toContain("Latest selected price");
    expect(html).toContain("Session date");
    expect(html).toContain("Latest selected FX");
    expect(html).toContain("Effective");
    expect(html).toContain("do not establish complete or current coverage");
    expect(html).not.toContain("Observed ");
  });
  it("keeps a missing snapshot distinct from an accepted empty snapshot", () => {
    const missing = portfolioFixture();
    missing.snapshot = null;
    missing.companies = [];
    missing.standalone_positions = [];
    missing.cash_valuations = [];
    missing.valuation_gaps = [];
    const absent = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={missing}
        rows={portfolioHoldingRows(missing)}
      />,
    );
    expect(absent).toContain("No accepted holdings snapshot");
    expect(absent).toContain(
      "Listing marks cannot be assessed without a holdings snapshot",
    );
    expect(absent).not.toContain("No cash recorded");
    expect(absent).not.toContain("0 recorded listing marks need");
    expect(absent).not.toContain(
      "No portfolio-specific valuation or target exception",
    );
    const empty = portfolioFixture();
    if (!empty.snapshot) throw new Error("Synthetic snapshot required");
    empty.snapshot.positions = [];
    empty.snapshot.cash_positions = [];
    const recorded = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={empty}
        rows={portfolioHoldingRows(empty)}
      />,
    );
    expect(recorded).toContain("No cash recorded");
    expect(recorded).toContain(
      "0 recorded listing marks need freshness or valuation review",
    );
  });
  it("does not infer a price gap for a listing without valuation context", () => {
    const overview = portfolioFixture();
    if (!overview.snapshot) throw new Error("Synthetic snapshot required");
    const unknownId = "20000000-0000-4000-8000-999999999999";
    overview.snapshot.positions.push({
      listing_id: unknownId,
      quantity: "1",
    } as (typeof overview.snapshot.positions)[number]);
    const row = portfolioHoldingRows(overview).find(
      (item) => item.listingId === unknownId,
    );
    expect(row?.valuationStatus).toBe("UNAVAILABLE");
    const html = renderToStaticMarkup(
      <PortfolioHoldingsSection
        overview={overview}
        rows={row ? [row] : []}
        onConfirmed={() => {}}
      />,
    );
    expect(html).toContain("UNAVAILABLE");
    expect(html).not.toContain("PRICE UNAVAILABLE");
    expect(html).not.toContain("/operations#market-data-refresh");
    expect(html).not.toContain("Review company prices");
  });
  it("does not describe a partial empty snapshot as complete", () => {
    const overview = portfolioFixture();
    if (!overview.snapshot) throw new Error("Synthetic snapshot required");
    overview.snapshot.completeness = "PARTIAL";
    overview.snapshot.positions = [];
    overview.snapshot.cash_positions = [];
    overview.companies = [];
    overview.valuation_gaps = [];
    const html = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
      />,
    );
    expect(html).toContain("Recorded security positions");
    expect(html).toContain("This snapshot is incomplete");
    expect(html).not.toContain(
      "No portfolio-specific valuation or target exception",
    );
  });
  it("shows every reported gap without inventing a listing identity", () => {
    const overview = portfolioFixture();
    overview.valuation_gaps = Array.from({ length: 6 }, (_, index) => ({
      identity: `synthetic-gap-${index + 1}`,
      reason: index === 5 ? "BALANCE_UNAVAILABLE" : "PRICE_UNAVAILABLE",
    }));
    const html = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
      />,
    );
    expect(html).toContain("6 valuation inputs unresolved");
    expect(html).toContain("Show remaining 2 valuation inputs");
    expect(html).toContain("synthetic-gap-6");
    expect(html).toContain("BALANCE UNAVAILABLE");
  });
  it("routes listing and cash gaps to their existing review destinations", () => {
    const overview = portfolioFixture();
    overview.companies[0].positions[0].valuation_status = "PRICE_UNAVAILABLE";
    overview.companies[1].positions[0].valuation_status = "FX_UNAVAILABLE";
    overview.companies[2].positions[0].valuation_status =
      "QUANTITY_UNAVAILABLE";
    overview.standalone_positions[0].valuation_status = "PRICE_UNAVAILABLE";
    const usd = overview.cash_valuations.find(
      (cash) => cash.currency === "USD",
    );
    if (!usd) throw new Error("Synthetic USD cash required");
    usd.valuation_status = "FX_UNAVAILABLE";
    const html = renderToStaticMarkup(
      <PortfolioHoldingsSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
        onConfirmed={() => {}}
      />,
    );
    const rows = html.match(/<tr class="align-top">.*?<\/tr>/g) ?? [];
    const price = rows.find((row) => row.includes("T01"));
    const fx = rows.find((row) => row.includes("T02"));
    const quantity = rows.find((row) => row.includes("T03"));
    const standalone = rows.find((row) => row.includes("SPYY"));
    expect(price).toContain(
      `/company/${overview.companies[0].company.id}?view=history`,
    );
    expect(price).not.toContain("operations#market-data-refresh");
    expect(fx).toContain("/operations#market-data-refresh");
    expect(fx).toContain(
      'aria-label="Review global price and FX status, from T02 NASDAQ"',
    );
    expect(quantity).toContain("#holdings-confirmation");
    expect(quantity).toContain('aria-label="Review holdings for T03 XETRA"');
    expect(quantity).not.toContain("operations#market-data-refresh");
    expect(standalone).toContain("/operations#market-data-refresh");
    const cash = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
      />,
    );
    expect(cash).toContain("/operations#market-data-refresh");
    expect(cash).toContain(
      'aria-label="Review global price and FX status, from USD cash"',
    );
  });
  it("directs ledger-owned quantity gaps to the ledger", () => {
    const overview = portfolioFixture();
    overview.holdings_authority = {
      source: "ACCEPTED_LEDGER",
      publication_id: "10000000-0000-4000-8000-000000000001",
      opening_snapshot_id: "10000000-0000-4000-8000-000000000002",
      cutover_at: "2026-10-10T12:00:00Z",
    };
    overview.companies[0].positions[0].valuation_status =
      "QUANTITY_UNAVAILABLE";
    const html = renderToStaticMarkup(
      <PortfolioHoldingsSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
        onConfirmed={() => {}}
      />,
    );
    expect(html).toContain('href="/portfolio/ledger"');
    expect(html).toContain("Review ledger");
  });
  it("explains native and foreign-currency cash without inventing rates", () => {
    const overview = portfolioFixture();
    const html = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
      />,
    );
    expect(html).toContain("No currency conversion required");
    expect(html).toContain("1 USD = 0.92 EUR");
    const usd = overview.cash_valuations.find(
      (cash) => cash.currency === "USD",
    );
    if (!usd) throw new Error("Synthetic USD cash required");
    usd.fx_rate = null;
    usd.fx_effective_at = null;
    const missing = renderToStaticMarkup(
      <PortfolioOverviewSection
        overview={overview}
        rows={portfolioHoldingRows(overview)}
      />,
    );
    expect(missing).toContain(
      "FX rate not recorded for this valuation (USD → EUR)",
    );
    expect(missing).not.toContain("1 USD = 0.92 EUR");
  });
});
