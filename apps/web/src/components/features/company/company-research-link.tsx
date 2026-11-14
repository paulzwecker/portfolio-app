"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { companyResearchHref } from "./company-navigation";
import type { CompanyView } from "./company-view-tabs";

/** Preserve research context only for links within the current company. */
export function CompanyResearchLink({
  companyId,
  view,
  children,
  className,
}: {
  companyId: string;
  view: CompanyView;
  children: ReactNode;
  className?: string;
}) {
  const query = useSearchParams();
  const sameCompany =
    usePathname() === `/company/${encodeURIComponent(companyId)}`;
  return (
    <Link
      className={className}
      href={companyResearchHref(companyId, {
        view,
        listingId: sameCompany ? query.get("listing") : null,
        fromPortfolio: sameCompany && query.get("from") === "portfolio",
      })}
    >
      {children}
    </Link>
  );
}
