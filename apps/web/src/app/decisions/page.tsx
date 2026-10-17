"use client";

import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/app/page-header";
import { PendingOrError } from "@/components/app/empty-state";
import { DecisionsWorkspace } from "@/components/features/decisions/decisions-workspace";
import { useResearch } from "@/hooks/use-research";
import { isPortfolios } from "@/lib/domain-contracts";

export default function DecisionsPage() {
  const state = useResearch("portfolios", isPortfolios);

  if (!state.data) {
    return (
      <>
        <PageHeader
          title="Decisions"
          description="Review strategic allocation, comparable opportunity context, and recorded execution timing."
        />
        <PendingOrError error={state.error} retry={state.retry} />
      </>
    );
  }

  if (state.data.length === 0) {
    return (
      <>
        <PageHeader
          title="Decisions"
          description="Review strategic allocation, comparable opportunity context, and recorded execution timing."
        />
        <Card>
          <CardContent className="py-10">
            <h2 className="text-lg font-medium">
              No portfolio decision context
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              No canonical portfolio has been returned. Create or restore the
              portfolio through the documented application workflow; the
              Decisions workspace does not seed example investment data.
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  return <DecisionsWorkspace id={state.data[0].id} />;
}
