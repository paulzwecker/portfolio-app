"use client";

import Link from "next/link";
import { PageHeader } from "@/components/app/page-header";
import { PendingOrError } from "@/components/app/empty-state";
import { PortfolioLedgerWorkspace } from "@/components/features/portfolio/portfolio-ledger-workspace";
import { useResearch } from "@/hooks/use-research";
import { isPortfolios } from "@/lib/domain-contracts";

export default function PortfolioLedgerPage() {
  const state = useResearch("portfolios", isPortfolios);
  if (!state.data)
    return (
      <>
        <PageHeader title="Transaction ledger review" />
        <PendingOrError error={state.error} retry={state.retry} />
      </>
    );
  if (state.data.length === 0)
    return (
      <div className="space-y-4">
        <PageHeader
          title="Transaction ledger review"
          description="A canonical portfolio and complete observed snapshot are required."
        />
        <Link href="/portfolio" className="text-sm underline">
          Open portfolio
        </Link>
      </div>
    );
  const portfolio = state.data[0];
  return (
    <PortfolioLedgerWorkspace
      key={portfolio.id}
      portfolioId={portfolio.id}
      portfolioName={portfolio.name}
    />
  );
}
