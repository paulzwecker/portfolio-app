import { AttentionCenter } from "@/components/attention-center";
import { PageTitle } from "@/components/research-frame";

export default function AttentionPage() {
  return (
    <>
      <PageTitle
        title="Attention Center"
        description="A concise, source-linked review of material portfolio and research changes. Each item preserves its canonical effective and recorded times."
      />
      <AttentionCenter />
    </>
  );
}
