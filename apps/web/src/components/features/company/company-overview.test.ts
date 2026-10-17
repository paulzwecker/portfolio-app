import { describe, expect, it } from "vitest";
import { selectPrimaryModelOutput } from "@/components/features/company/company-overview";
import type {
  CompanyModelOutputsCurrent,
  ModelOutputCurrentModel,
} from "@/lib/domain-contracts";

const model = (
  status: ModelOutputCurrentModel["status"],
  outputQuality: "COMPLETE" | "PARTIAL" = "PARTIAL",
) =>
  ({
    model_key: `${status}-${outputQuality}`,
    status,
    snapshot: { output_quality: outputQuality },
  }) as ModelOutputCurrentModel;

describe("Company overview model summary", () => {
  it("prefers a published complete output without recalculating values", () => {
    const value = {
      models: [
        model("PUBLISHED", "PARTIAL"),
        model("PUBLISHED", "COMPLETE"),
        model("PARTIAL", "COMPLETE"),
      ],
    } as CompanyModelOutputsCurrent;

    expect(selectPrimaryModelOutput(value)?.model_key).toBe(
      "PUBLISHED-COMPLETE",
    );
  });

  it("keeps unavailable and incomplete model states explicit", () => {
    expect(selectPrimaryModelOutput(undefined)).toBeNull();
    expect(
      selectPrimaryModelOutput({
        models: [],
      } as unknown as CompanyModelOutputsCurrent),
    ).toBeNull();
    expect(
      selectPrimaryModelOutput({
        models: [model("DATA_CHECK", "PARTIAL")],
      } as CompanyModelOutputsCurrent)?.status,
    ).toBe("DATA_CHECK");
  });
});
