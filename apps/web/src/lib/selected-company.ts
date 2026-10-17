export type SelectedCompany = {
  id: string;
  name: string;
  listings: Array<{ ticker: string; venue: string; currency: string | null }>;
};

const storageKey = "portfolio:selected-company:v1";
const eventName = "portfolio:selected-company";

export function readSelectedCompany(): SelectedCompany | null {
  if (typeof window === "undefined") return null;
  try {
    const parsed: unknown = JSON.parse(
      window.localStorage.getItem(storageKey) ?? "null",
    );
    if (!parsed || typeof parsed !== "object") return null;
    const candidate = parsed as Record<string, unknown>;
    if (typeof candidate.id !== "string" || typeof candidate.name !== "string")
      return null;
    const listings = Array.isArray(candidate.listings)
      ? candidate.listings.filter(
          (listing): listing is SelectedCompany["listings"][number] =>
            !!listing &&
            typeof listing === "object" &&
            typeof (listing as Record<string, unknown>).ticker === "string" &&
            typeof (listing as Record<string, unknown>).venue === "string" &&
            ((listing as Record<string, unknown>).currency === null ||
              typeof (listing as Record<string, unknown>).currency ===
                "string"),
        )
      : [];
    return { id: candidate.id, name: candidate.name, listings };
  } catch {
    return null;
  }
}

export function saveSelectedCompany(company: SelectedCompany) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey, JSON.stringify(company));
  window.dispatchEvent(
    new CustomEvent<SelectedCompany>(eventName, { detail: company }),
  );
}

export function selectedCompanyEventName() {
  return eventName;
}
