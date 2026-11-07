import { CompanyExplorerWorkspace } from "@/components/features/company/company-explorer-workspace";
import { Suspense } from "react";
import { LoadingSkeleton } from "@/components/app/loading-skeleton";

export default async function CompanyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense fallback={<LoadingSkeleton />}>
      <CompanyExplorerWorkspace companyId={id} />
    </Suspense>
  );
}
