// Fictional, deterministic API payload. Contains no workbook or portfolio data.
export const modelId = "99999999-9999-4999-8999-999999999999";
export const revisionId = "22222222-2222-4222-8222-222222222222";
export const malformedModelId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

export function sensitivityFixture() {
  return {
    calculation_version: "ufcf-dcf-sensitivity-v1",
    model_id: modelId,
    revision_id: revisionId,
    revision_number: 1,
    methodology_version: "ufcf-dcf-fade-v1",
    model_currency: "USD",
    discount_rate_shifts: ["-0.01", "0", "0.01"],
    terminal_growth_shifts: ["-0.005", "0", "0.005"],
    scenarios: ["BEAR", "BASE", "BULL"].map((scenario) => ({
      scenario,
      probability: scenario === "BASE" ? "0.6" : "0.2",
      year5_discount_rate: "0.09",
      terminal_growth: "0.025",
    })),
    cells: ["-0.01", "0", "0.01"].flatMap((discount_rate_shift) =>
      ["-0.005", "0", "0.005"].map((terminal_growth_shift) => ({
        discount_rate_shift,
        terminal_growth_shift,
        status: "AVAILABLE",
        unavailable_reason: /** @type {string | null} */ (null),
        bear_fv: /** @type {string | null} */ ("15"),
        base_fv: /** @type {string | null} */ ("20"),
        bull_fv: /** @type {string | null} */ ("30"),
        weighted_fv: /** @type {string | null} */ ("21"),
      })),
    ),
  };
}
