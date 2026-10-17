/** Presentation only. Preserve exact decimal text for observed quantities. */
export function quantity(value: string | null): string {
  if (value === null) return "Unknown";
  return value.includes(".")
    ? value.replace(/0+$/, "").replace(/\.$/, "")
    : value;
}

export function formatNumber(
  value: string | null,
  maximumFractionDigits = 2,
  missing = "Unavailable",
  locale = "en",
): string {
  if (value === null) return missing;
  return new Intl.NumberFormat(locale, { maximumFractionDigits }).format(
    Number(value),
  );
}

/** Compact statement-table display only; exact source decimals remain in the drawer. */
export function formatCompactFinancial(
  value: string | null,
  digits = 2,
): string {
  if (value === null) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "Unavailable";
  const formatted = new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: digits,
  }).format(Math.abs(numeric));
  return numeric < 0 ? `(${formatted})` : formatted;
}

export function formatCurrency(
  value: string | null,
  currencyCode: string | null,
  maximumFractionDigits = 2,
  missing = "Unavailable",
  locale = "en",
): string {
  if (value === null) return missing;
  if (!currencyCode) return quantity(value);
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currencyCode,
      maximumFractionDigits,
    }).format(Number(value));
  } catch {
    return `${quantity(value)} ${currencyCode}`;
  }
}

export function formatPercent(
  value: string | null,
  maximumFractionDigits = 10,
  missing = "No target",
  locale = "en",
): string {
  return value === null
    ? missing
    : new Intl.NumberFormat(locale, {
        style: "percent",
        maximumFractionDigits,
      }).format(Number(value));
}

export function formatMetric(
  value: string | null,
  options: {
    currencyCode?: string | null;
    unit?: string | null;
    maximumFractionDigits?: number;
    missing?: string;
  } = {},
) {
  const {
    currencyCode = null,
    unit = null,
    maximumFractionDigits = 2,
    missing = "Unavailable",
  } = options;
  if (value === null) return missing;
  const formatted = currencyCode
    ? formatCurrency(value, currencyCode, maximumFractionDigits, missing)
    : formatNumber(value, maximumFractionDigits, missing);
  return unit && !currencyCode ? `${formatted} ${unit}` : formatted;
}

/** Keep the existing high-precision behavior for rates and tiny non-zero values. */
export function percent(value: string | null): string {
  return formatPercent(value, 10, "No target");
}

export function statusLabel(value: string | null | undefined): string {
  return (
    value?.trim().replaceAll("_", " ").replaceAll("-", " ") || "Unavailable"
  );
}

export function date(value: string): string {
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** Timestamp display uses the viewer's local timezone and includes its abbreviation. */
export function dateTime(value: string | null | undefined): string {
  if (!value) return "Unknown time";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return new Intl.DateTimeFormat([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(parsed);
}

/** Date-only values are formatted in their stated timezone (UTC by default). */
export function dateOnly(value: string, timeZone = "UTC"): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return new Intl.DateTimeFormat([], {
    dateStyle: "medium",
    timeZone,
  }).format(parsed);
}

/** Market dates are stored at UTC midnight and have date, not close-time, precision. */
export function marketDate(value: string): string {
  return dateOnly(value, "UTC");
}
