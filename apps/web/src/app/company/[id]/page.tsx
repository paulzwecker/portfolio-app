import { CompanyExplorerWorkspace } from "@/components/features/company/company-explorer-workspace";

export default async function CompanyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CompanyExplorerWorkspace companyId={id} />;
}
