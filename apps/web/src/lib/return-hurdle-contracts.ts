import type { components } from "@portfolio/contracts";
import {
  isExpectedReturnMarketPrice,
  isRecord,
  isReturnMethodology,
} from "@/lib/domain-contracts";

export type ReturnHurdle = components["schemas"]["ReturnHurdleRead"];

/** Normalize exact decimal text for request/response identity, without rounding. */
export function normalizedDecimalText(value: string): string | null {
  if (value.length > 256 || !/^-?\d+(?:\.\d+)?$/.test(value)) return null;
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  const integer = whole.replace(/^0+(?=\d)/, "");
  const tail = fraction.replace(/0+$/, "");
  const normalized = integer + (tail ? `.${tail}` : "");
  return negative && normalized !== "0" ? `-${normalized}` : normalized;
}

export function sameDecimalText(left: string, right: string): boolean {
  const normalized = normalizedDecimalText(left);
  return normalized !== null && normalized === normalizedDecimalText(right);
}

/** Presentation-unit conversion only: a typed percent becomes an exact API ratio. */
export function requiredReturnFromPercent(value: string): string | null {
  const trimmed = value.trim();
  if (!/^\d{1,3}(?:\.\d{1,8})?$/.test(trimmed)) return null;
  const [whole, fraction = ""] = trimmed.split(".");
  const integer = whole.replace(/^0+(?=\d)/, "");
  if (integer.length > 2) return null;
  const padded = integer.padStart(3, "0");
  return normalizedDecimalText(
    `${padded.slice(0, -2)}.${padded.slice(-2)}${fraction}`,
  );
}

export function hypotheticalEntryPrice(value: string): string | null {
  const trimmed = value.trim();
  if (!/^\d{1,18}(?:\.\d{1,10})?$/.test(trimmed)) return null;
  const normalized = normalizedDecimalText(trimmed);
  return normalized === "0" ? null : normalized;
}

const text = (value: unknown): value is string => typeof value === "string";
const nullableText = (value: unknown) => value === null || text(value);
const decimal = (value: unknown): value is string =>
  text(value) &&
  normalizedDecimalText(value) !== null &&
  Number.isFinite(Number(value));
const nullableDecimal = (value: unknown) => value === null || decimal(value);
const positive = (value: unknown): value is string =>
  decimal(value) &&
  !value.startsWith("-") &&
  normalizedDecimalText(value) !== "0";
const ratio = (value: unknown) => {
  if (!decimal(value)) return false;
  const normalized = normalizedDecimalText(value)!;
  return /^0(?:\.\d+)?$/.test(normalized) || normalized === "1";
};
const uuid = (value: unknown) =>
  text(value) && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
const timestamp = (value: unknown) =>
  text(value) && Number.isFinite(Date.parse(value));

export function isReturnHurdle(value: unknown): value is ReturnHurdle {
  if (
    !isRecord(value) ||
    value.calculation_version !== "native-return-hurdle-v1" ||
    !uuid(value.company_id) ||
    !uuid(value.model_id) ||
    !uuid(value.revision_id) ||
    !uuid(value.valuation_listing_id) ||
    !text(value.model_name) ||
    !text(value.ticker) ||
    !text(value.venue) ||
    ![
      "UFCF_DCF_10Y_FADE",
      "OWNER_CASH_FLOW_10Y",
      "RESIDUAL_INCOME_10Y_FADE",
    ].includes(value.model_type as string) ||
    !text(value.model_currency) ||
    !/^[A-Z]{3}$/.test(value.model_currency) ||
    !Number.isInteger(value.revision_number) ||
    Number(value.revision_number) < 1 ||
    !text(value.methodology_version) ||
    !nullableText(value.source) ||
    !timestamp(value.effective_at) ||
    !timestamp(value.recorded_at) ||
    !timestamp(value.calculated_at) ||
    !isReturnMethodology(value.return_methodology) ||
    !ratio(value.required_return) ||
    sameDecimalText(value.required_return as string, "1") ||
    !decimal(value.accepted_hurdle) ||
    !["AVAILABLE", "UNAVAILABLE"].includes(value.status as string) ||
    !nullableText(value.unavailable_reason) ||
    !nullableDecimal(value.weighted_entry_price) ||
    !nullableDecimal(value.reconciled_irr) ||
    !Array.isArray(value.scenarios) ||
    value.scenarios.length !== 3 ||
    !value.scenarios.every(
      (row: unknown) =>
        isRecord(row) &&
        ["BEAR", "BASE", "BULL"].includes(row.scenario as string) &&
        ratio(row.probability) &&
        ["AVAILABLE", "UNAVAILABLE"].includes(row.status as string) &&
        nullableDecimal(row.required_entry_price) &&
        nullableText(row.unavailable_reason) &&
        (row.status === "AVAILABLE"
          ? positive(row.required_entry_price)
          : row.required_entry_price === null),
    ) ||
    new Set(value.scenarios.map((row) => row.scenario)).size !== 3 ||
    !Array.isArray(value.cash_flows) ||
    value.cash_flows.length !== 10 ||
    !value.cash_flows.every(
      (row: unknown) =>
        isRecord(row) &&
        Number.isInteger(row.forecast_year) &&
        Number(row.forecast_year) >= 1 &&
        Number(row.forecast_year) <= 10 &&
        decimal(row.annual_cash_flow_per_share) &&
        decimal(row.terminal_cash_flow_per_share),
    ) ||
    new Set(value.cash_flows.map((row) => row.forecast_year)).size !==
      value.cash_flows.length ||
    !nullableDecimal(value.hypothetical_entry_price) ||
    !nullableDecimal(value.hypothetical_expected_irr) ||
    !["NOT_REQUESTED", "AVAILABLE", "UNAVAILABLE"].includes(
      value.hypothetical_status as string,
    ) ||
    !nullableText(value.hypothetical_unavailable_reason) ||
    !isExpectedReturnMarketPrice(value.market_price) ||
    !nullableDecimal(value.current_price) ||
    !nullableDecimal(value.current_expected_irr) ||
    !nullableDecimal(value.current_price_gap_to_required)
  )
    return false;

  const codes = {
    UFCF_DCF_10Y_FADE: ["UFCF_ENTERPRISE_IRR", "UFCF_ENTERPRISE_HMODEL_IRR"],
    OWNER_CASH_FLOW_10Y: ["OWNER_CASH_FLOW_EQUITY_IRR"],
    RESIDUAL_INCOME_10Y_FADE: ["RESIDUAL_INCOME_EQUITY_IRR"],
  };
  if (
    !codes[value.model_type as keyof typeof codes].includes(
      value.return_methodology.code,
    ) ||
    value.return_methodology.perspective !==
      (value.model_type === "UFCF_DCF_10Y_FADE" ? "ENTERPRISE" : "EQUITY")
  )
    return false;

  if (
    value.contributions !== null &&
    (!isRecord(value.contributions) ||
      !decimal(value.contributions.annual_cash_flow_pv_per_share) ||
      !decimal(value.contributions.terminal_pv_per_share) ||
      !decimal(value.contributions.opening_balance_sheet_per_share))
  )
    return false;
  if (
    value.status === "AVAILABLE" &&
    (!positive(value.weighted_entry_price) ||
      !decimal(value.reconciled_irr) ||
      value.contributions === null ||
      value.cash_flows.length !== 10)
  )
    return false;
  if (
    value.status === "UNAVAILABLE" &&
    (value.weighted_entry_price !== null ||
      value.reconciled_irr !== null ||
      value.contributions !== null)
  )
    return false;
  if (
    value.hypothetical_status === "NOT_REQUESTED" &&
    (value.hypothetical_entry_price !== null ||
      value.hypothetical_expected_irr !== null)
  )
    return false;
  if (
    value.hypothetical_status === "AVAILABLE" &&
    (!positive(value.hypothetical_entry_price) ||
      !decimal(value.hypothetical_expected_irr))
  )
    return false;
  if (
    value.hypothetical_status === "UNAVAILABLE" &&
    value.hypothetical_expected_irr !== null
  )
    return false;
  if (
    value.current_price !== null &&
    (!positive(value.current_price) ||
      value.market_price.status !== "AVAILABLE" ||
      value.market_price.listing_id !== value.valuation_listing_id ||
      value.market_price.model_currency !== value.model_currency ||
      value.market_price.quote_currency !== value.model_currency ||
      !positive(value.market_price.model_reference_price) ||
      !sameDecimalText(
        value.current_price,
        value.market_price.model_reference_price,
      ))
  )
    return false;
  if (
    value.current_price === null &&
    (value.current_expected_irr !== null ||
      value.current_price_gap_to_required !== null)
  )
    return false;
  return true;
}

export function matchesReturnHurdleRequest(
  data: ReturnHurdle,
  request: {
    modelId: string;
    revisionId: string;
    requiredReturn: string;
    entryPrice: string | null;
  },
): boolean {
  return (
    data.model_id === request.modelId &&
    data.revision_id === request.revisionId &&
    sameDecimalText(data.required_return, request.requiredReturn) &&
    (request.entryPrice === null
      ? data.hypothetical_entry_price === null
      : data.hypothetical_entry_price !== null &&
        sameDecimalText(data.hypothetical_entry_price, request.entryPrice))
  );
}
