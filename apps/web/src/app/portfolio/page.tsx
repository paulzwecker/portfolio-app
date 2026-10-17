"use client";

import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/app/page-header";
import { PendingOrError } from "@/components/app/empty-state";
import { PortfolioWorkspace } from "@/components/features/portfolio/portfolio-workspace";
import { useResearch } from "@/hooks/use-research";
import { isPortfolios } from "@/lib/domain-contracts";

export default function PortfolioPage() {
  const state = useResearch("portfolios", isPortfolios);

  if (!state.data) {
    return (
      <>
        <PageHeader
          title="Portfolio"
          description="Current ownership, valuation and strategic position."
        />
        <PendingOrError error={state.error} retry={state.retry} />
      </>
    );
  }

  if (state.data.length === 0) {
    return (
      <>
        <PageHeader
          title="Portfolio"
          description="Current ownership and strategic targets remain separate."
        />
        <Card>
          <CardContent className="py-10">
            <h2 className="text-lg font-medium">No portfolio yet</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Create a logical portfolio through the API or use the documented
              development seed to explore fictional examples.
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  return <PortfolioWorkspace id={state.data[0].id} />;
}
