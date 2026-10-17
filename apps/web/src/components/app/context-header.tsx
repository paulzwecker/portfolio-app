"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { CompanyFinder } from "@/components/app/company-finder";
import {
  readSelectedCompany,
  selectedCompanyEventName,
  type SelectedCompany,
} from "@/lib/selected-company";

function currentLabel(pathname: string, selected: SelectedCompany | null) {
  if (pathname === "/") return "Overview";
  if (pathname === "/portfolio") return "Portfolio";
  if (pathname === "/decisions") return "Decisions";
  if (pathname === "/universe") return "Universe";
  if (pathname === "/attention") return "Attention Center";
  if (pathname === "/operations") return "Operations";
  if (pathname.startsWith("/company/"))
    return selected?.name ?? "Company Explorer";
  if (pathname === "/design-system") return "Design system";
  return "Portfolio Research";
}

export function ContextHeader() {
  const pathname = usePathname();
  const [selected, setSelected] = useState<SelectedCompany | null>(null);
  useEffect(() => {
    const sync = () => setSelected(readSelectedCompany());
    sync();
    window.addEventListener(selectedCompanyEventName(), sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(selectedCompanyEventName(), sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const crumb = currentLabel(pathname, selected);
  const selectedPath = selected
    ? `/company/${encodeURIComponent(selected.id)}`
    : null;

  return (
    <div className="grid min-w-0 flex-1 grid-cols-1 items-center gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(14rem,22rem)]">
      <nav
        aria-label="Breadcrumb"
        className="hidden min-w-0 items-center gap-2 text-sm sm:flex"
      >
        <Link
          href="/"
          className="shrink-0 text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        >
          Overview
        </Link>
        {pathname !== "/" && (
          <>
            <ChevronRight
              aria-hidden="true"
              className="size-3.5 shrink-0 text-muted-foreground"
            />
            <span aria-current="page" className="truncate font-medium">
              {crumb}
            </span>
          </>
        )}
        {selectedPath && !pathname.startsWith("/company/") && (
          <span className="ml-2 hidden truncate text-xs text-muted-foreground lg:inline">
            · {selected?.name}
          </span>
        )}
      </nav>
      <div className="sm:hidden">
        <span className="block truncate text-sm font-medium">{crumb}</span>
        {selectedPath && !pathname.startsWith("/company/") && (
          <Link
            href={selectedPath}
            className="block truncate text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            Selected company · {selected?.name}
          </Link>
        )}
      </div>
      <div className="min-w-0">
        <CompanyFinder />
      </div>
      {selectedPath && pathname.startsWith("/company/") && (
        <div className="col-span-full hidden min-w-0 items-center gap-4 border-t pt-2 text-xs sm:flex">
          <Link
            href={selectedPath}
            className="font-medium text-foreground hover:underline"
          >
            Company Explorer
          </Link>
          <Link
            href={`${selectedPath}#canonical-models`}
            className="text-muted-foreground hover:text-foreground hover:underline"
          >
            Modeling
          </Link>
          <Link
            href={`${selectedPath}#source-documents`}
            className="text-muted-foreground hover:text-foreground hover:underline"
          >
            Research evidence
          </Link>
        </div>
      )}
    </div>
  );
}
