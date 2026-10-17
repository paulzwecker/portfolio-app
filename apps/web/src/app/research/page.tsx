import {
  ResearchWorkspace,
  type ResearchView,
} from "@/components/features/research/research-workspace";

const views = new Set<ResearchView>([
  "pipeline",
  "queue",
  "reviews",
  "changes",
]);

export default async function ResearchPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string | string[] }>;
}) {
  const params = await searchParams;
  const value = Array.isArray(params.view) ? params.view[0] : params.view;
  const initialView = views.has(value as ResearchView)
    ? (value as ResearchView)
    : "queue";
  return <ResearchWorkspace initialView={initialView} />;
}
