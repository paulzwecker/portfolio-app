import { OperationsOverview } from "@/components/features/operations/operations-overview";

export default async function OperationsPage({
  searchParams,
}: {
  searchParams: Promise<{ company?: string | string[] }>;
}) {
  const { company } = await searchParams;
  const companyId =
    typeof company === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      company,
    )
      ? company
      : undefined;
  return <OperationsOverview companyId={companyId} />;
}
