import { formatCurrency, formatPercent } from "@/lib/display";
export function formatPrice(value: string | null, currency: string | null) {
  return formatCurrency(value, currency, 4, "Unavailable", "en");
}

export function rateLabel(value: string | null) {
  return formatPercent(value, 1, "Unavailable", "en");
}

export function modelValue(value: string | null, currency: string | null) {
  return formatCurrency(value, currency, 2, "Not supplied", "en");
}

export function modelPercent(value: string | null) {
  return formatPercent(value, 2, "Not supplied", "en");
}
