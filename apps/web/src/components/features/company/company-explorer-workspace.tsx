"use client";

import { useEffect, useState } from "react";
import { PageHeader as PageTitle } from "@/components/app/page-header";
import { PendingOrError } from "@/components/app/empty-state";
import { useResearch } from "@/hooks/use-research";
import { isDetail, isListingMarketDataList } from "@/lib/domain-contracts";
import { saveSelectedCompany } from "@/lib/selected-company";
import { CompanyIdentityHeader } from "@/components/features/company/company-identity-header";
import { CompanyInvestmentThesis } from "@/components/features/company/company-investment-thesis";
import { CompanyResearchEvidenceWorkspace } from "@/components/features/company/company-research-evidence-workspace";
import {
  CompanyViewTabs,
  companyViewFromLocation,
  type CompanyView,
} from "@/components/features/company/company-view-tabs";
import { CompanyOverview } from "@/components/features/company/company-overview";
import { CompanyValuationWorkspace } from "@/components/features/company/company-valuation-workspace";
import { InvestmentQuality as CompanyInvestmentQuality } from "@/components/features/company/company-investment-quality";
import { FinancialStatementsWorkspace } from "@/components/features/company/financial-statements/financial-statements-workspace";
import { CompanyHistoricalAnalysisWorkspace } from "@/components/features/company/company-historical-analysis-workspace";
import { CompanyRefreshAction } from "@/components/features/operations/company-refresh-action";
export function CompanyExplorerWorkspace({ companyId }: { companyId: string }) {
  const id = companyId;
  const [view, setView] = useState<CompanyView>("overview");
  const state = useResearch(`companies/${encodeURIComponent(id)}`, isDetail);
  const marketState = useResearch(
    `companies/${encodeURIComponent(id)}/market-data?history_limit=252`,
    isListingMarketDataList,
  );
  const detail = state.data;

  useEffect(() => {
    const syncFromLocation = () =>
      setView(
        companyViewFromLocation(window.location.search, window.location.hash),
      );
    syncFromLocation();
    window.addEventListener("popstate", syncFromLocation);
    window.addEventListener("hashchange", syncFromLocation);
    return () => {
      window.removeEventListener("popstate", syncFromLocation);
      window.removeEventListener("hashchange", syncFromLocation);
    };
  }, []);

  useEffect(() => {
    const targetId = window.location.hash.slice(1);
    if (!targetId) return;
    const frame = window.requestAnimationFrame(() =>
      document.getElementById(targetId)?.scrollIntoView({ block: "start" }),
    );
    return () => window.cancelAnimationFrame(frame);
  }, [view]);

  const selectView = (next: CompanyView) => {
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    url.hash = "";
    window.history.replaceState(window.history.state, "", url);
  };

  useEffect(() => {
    if (!detail) return;
    saveSelectedCompany({
      id: detail.company.id,
      name: detail.company.name,
      listings: detail.listings.map((listing) => ({
        ticker: listing.ticker,
        venue: listing.venue,
        currency: listing.currency ?? null,
      })),
    });
  }, [detail]);
  if (!detail)
    return (
      <>
        <PageTitle
          title="Company"
          description="Identity, investment lifecycle and portfolio context."
        />
        <PendingOrError {...state} />
      </>
    );

  return (
    <>
      <CompanyIdentityHeader
        detail={detail}
        marketState={marketState}
        actions={<CompanyRefreshAction companyId={detail.company.id} />}
      />
      <CompanyViewTabs value={view} onChange={selectView} />
      <div
        id="company-view-panel"
        role="tabpanel"
        aria-labelledby={`company-tab-${view}`}
        tabIndex={0}
        className="min-w-0 space-y-8 outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {view === "overview" && (
          <CompanyOverview detail={detail} lifecycleChanged={state.retry} />
        )}
        {view === "financials" && (
          <FinancialStatementsWorkspace companyId={detail.company.id} />
        )}
        {view === "valuation" && (
          <CompanyValuationWorkspace
            companyId={detail.company.id}
            listings={detail.listings}
          />
        )}
        {view === "thesis" && (
          <>
            <CompanyInvestmentThesis
              companyId={detail.company.id}
              companyName={detail.company.name}
            />
            <CompanyInvestmentQuality companyId={detail.company.id} />
          </>
        )}
        {view === "research" && (
          <CompanyResearchEvidenceWorkspace
            companyId={detail.company.id}
            companyName={detail.company.name}
          />
        )}
        {view === "history" && (
          <CompanyHistoricalAnalysisWorkspace
            companyId={detail.company.id}
            marketState={marketState}
          />
        )}
      </div>
    </>
  );
}
