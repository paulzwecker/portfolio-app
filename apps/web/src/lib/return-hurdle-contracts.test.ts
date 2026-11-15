import { describe, expect, it } from "vitest";
import { returnHurdleFixture } from "../../e2e/fixtures/return-hurdle";
import {
  hypotheticalEntryPrice,
  isReturnHurdle,
  matchesReturnHurdleRequest,
  normalizedDecimalText,
  requiredReturnFromPercent,
  sameDecimalText,
} from "./return-hurdle-contracts";

describe("Return hurdle presentation input", () => {
  it("converts user percentages exactly without inventing a default", () => {
    expect(requiredReturnFromPercent("")).toBeNull();
    expect(requiredReturnFromPercent("0")).toBe("0");
    expect(requiredReturnFromPercent("12.34567890")).toBe("0.123456789");
    expect(requiredReturnFromPercent(" 009.05 ")).toBe("0.0905");
    expect(requiredReturnFromPercent("0.00000001")).toBe("0.0000000001");
    expect(requiredReturnFromPercent("99.99999999")).toBe("0.9999999999");
    for (const invalid of [
      "100",
      "-1",
      "Infinity",
      "1e1",
      "12,5",
      ".1",
      "1.000000001",
    ])
      expect(requiredReturnFromPercent(invalid)).toBeNull();
  });
  it("preserves exact positive price text including values beyond Number precision", () => {
    expect(hypotheticalEntryPrice("00023.4500")).toBe("23.45");
    expect(hypotheticalEntryPrice("9007199254740993.0000000001")).toBe(
      "9007199254740993.0000000001",
    );
    for (const invalid of [
      "",
      "0",
      "0.000",
      "-2",
      "1e3",
      "1,000",
      "1.12345678901",
    ])
      expect(hypotheticalEntryPrice(invalid)).toBeNull();
    expect(sameDecimalText("000.1200", "0.12")).toBe(true);
    expect(sameDecimalText("9007199254740993", "9007199254740992")).toBe(false);
    expect(normalizedDecimalText("-0.000")).toBe("0");
    expect(sameDecimalText("NaN", "NaN")).toBe(false);
  });
});

describe("Return hurdle read contract", () => {
  it("accepts a complete read-only result without a live quote", () => {
    const data = returnHurdleFixture();
    expect(isReturnHurdle(data)).toBe(true);
    const request = {
      modelId: data.model_id,
      revisionId: data.revision_id,
      requiredReturn: "0.1200",
      entryPrice: null,
    };
    expect(matchesReturnHurdleRequest(data, request)).toBe(true);
    expect(
      matchesReturnHurdleRequest(data, { ...request, requiredReturn: "0.15" }),
    ).toBe(false);
    expect(
      matchesReturnHurdleRequest(data, {
        ...request,
        revisionId: data.company_id,
      }),
    ).toBe(false);
    expect(
      matchesReturnHurdleRequest(data, { ...request, entryPrice: "20" }),
    ).toBe(false);
  });
  it("keeps a valid unavailable calculation explicit", () => {
    const data = returnHurdleFixture();
    data.status = "UNAVAILABLE";
    data.weighted_entry_price = null;
    data.reconciled_irr = null;
    data.contributions = null;
    data.unavailable_reason =
      "The accepted stream has no positive entry value at this return.";
    data.hypothetical_entry_price = "0.5";
    data.hypothetical_status = "UNAVAILABLE";
    data.hypothetical_unavailable_reason =
      "No conventional IRR exists at this entry.";
    expect(isReturnHurdle(data)).toBe(true);
  });
  it("rejects malformed, incomplete and contradictory result fields", () => {
    const data = returnHurdleFixture();
    for (const patch of [
      { required_return: "1" },
      { required_return: "NaN" },
      { model_currency: "US" },
      { status: "AVAILABLE", weighted_entry_price: null },
      {
        hypothetical_status: "NOT_REQUESTED",
        hypothetical_expected_irr: "0.2",
      },
      {
        hypothetical_status: "AVAILABLE",
        hypothetical_entry_price: "-3",
        hypothetical_expected_irr: "0.2",
      },
      { current_price: "18" },
      { current_expected_irr: "0.1" },
      { scenarios: [data.scenarios[0], data.scenarios[0], data.scenarios[2]] },
      { cash_flows: data.cash_flows.slice(0, 9) },
    ])
      expect(isReturnHurdle({ ...data, ...patch })).toBe(false);
  });
  it("only displays current-price analysis for the same fresh listing and currency", () => {
    const data = returnHurdleFixture();
    data.current_price = "20";
    data.market_price.status = "AVAILABLE";
    data.market_price.quote_currency = "USD";
    data.market_price.model_reference_price = "20";
    expect(isReturnHurdle(data)).toBe(true);
    data.market_price.quote_currency = "EUR";
    expect(isReturnHurdle(data)).toBe(false);
    data.market_price.quote_currency = "USD";
    data.market_price.status = "STALE";
    expect(isReturnHurdle(data)).toBe(false);
    data.market_price.status = "AVAILABLE";
    data.market_price.listing_id = data.company_id;
    expect(isReturnHurdle(data)).toBe(false);
  });

  it("rejects a misleading return perspective or a changed reference quote", () => {
    const data = returnHurdleFixture();
    data.return_methodology.perspective = "EQUITY";
    expect(isReturnHurdle(data)).toBe(false);
    data.return_methodology.perspective = "ENTERPRISE";
    data.current_price = "20";
    data.market_price.status = "AVAILABLE";
    data.market_price.quote_currency = "USD";
    data.market_price.model_reference_price = "21";
    expect(isReturnHurdle(data)).toBe(false);
  });
});
