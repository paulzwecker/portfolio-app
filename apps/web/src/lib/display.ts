/** Presentation only. Preserve exact decimal text for observed quantities. */
export function quantity(value: string | null): string {
  if (value === null) return "Unknown";
  return value.includes(".")
    ? value.replace(/0+$/, "").replace(/\.$/, "")
    : value;
}

export function percent(value: string | null): string {
  return value === null
    ? "No target"
    : new Intl.NumberFormat("en", {
        style: "percent",
        maximumFractionDigits: 10,
      }).format(Number(value));
}

export function date(value: string): string {
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
