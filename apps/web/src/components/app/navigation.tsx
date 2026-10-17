"use client";

import { useEffect, useState } from "react";
import {
  BookOpen,
  BriefcaseBusiness,
  Building2,
  ClipboardList,
  Home,
  Menu,
  PanelLeftClose,
  Settings2,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  readSelectedCompany,
  selectedCompanyEventName,
  type SelectedCompany,
} from "@/lib/selected-company";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const mainItems = [
  {
    href: "/",
    label: "Overview",
    icon: Home,
    match: (path: string) => path === "/",
  },
  {
    href: "/portfolio",
    label: "Portfolio",
    icon: BriefcaseBusiness,
    match: (path: string) => path === "/portfolio",
  },
  {
    href: "/decisions",
    label: "Decisions",
    icon: ClipboardList,
    match: (path: string) => path === "/decisions",
  },
];

const researchItems = [
  {
    href: "/universe",
    label: "Universe",
    icon: BookOpen,
    match: (path: string) => path.startsWith("/universe"),
  },
  {
    href: "/research",
    label: "Research",
    icon: ClipboardList,
    match: (path: string) => path.startsWith("/research"),
  },
];

function NavigationLink({
  href,
  label,
  icon: Icon,
  active,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: typeof Home;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      className={cn(
        "flex min-h-10 items-center gap-2.5 rounded-md px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
        active
          ? "bg-sidebar-accent font-medium text-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/70",
      )}
    >
      <Icon aria-hidden="true" className="size-4 shrink-0 text-primary" />
      <span>{label}</span>
    </Link>
  );
}

export function Navigation() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hash, setHash] = useState("");
  const [selected, setSelected] = useState<SelectedCompany | null>(null);

  useEffect(() => {
    const updateHash = () => setHash(window.location.hash);
    updateHash();
    window.addEventListener("hashchange", updateHash);
    const onSelected = (event: Event) => {
      const company = (event as CustomEvent<SelectedCompany>).detail;
      setSelected(company);
    };
    const initialSync = window.setTimeout(
      () => setSelected(readSelectedCompany()),
      0,
    );
    window.addEventListener(selectedCompanyEventName(), onSelected);
    window.addEventListener("storage", updateSelectedFromStorage);
    function updateSelectedFromStorage() {
      setSelected(readSelectedCompany());
    }
    return () => {
      window.clearTimeout(initialSync);
      window.removeEventListener("hashchange", updateHash);
      window.removeEventListener(selectedCompanyEventName(), onSelected);
      window.removeEventListener("storage", updateSelectedFromStorage);
    };
  }, []);

  const selectedPath = selected
    ? `/company/${encodeURIComponent(selected.id)}`
    : null;
  const isCompanyPage = pathname.startsWith("/company/");

  function links(onNavigate?: () => void) {
    return (
      <div className="space-y-5">
        <NavigationGroup title="Workspace">
          {mainItems.map((item) => (
            <NavigationLink
              key={item.href}
              {...item}
              active={
                item.label === "Decisions"
                  ? pathname === "/decisions" ||
                    (pathname === "/portfolio" &&
                      hash === "#portfolio-rank-heading")
                  : item.match(pathname) &&
                    !(
                      item.label === "Portfolio" &&
                      hash === "#portfolio-rank-heading"
                    )
              }
              onNavigate={onNavigate}
            />
          ))}
        </NavigationGroup>
        <NavigationGroup title="Research">
          {researchItems.map((item) => (
            <NavigationLink
              key={item.href}
              {...item}
              active={item.match(pathname)}
              onNavigate={onNavigate}
            />
          ))}
        </NavigationGroup>
        <NavigationGroup title="Company">
          {selectedPath ? (
            <>
              <NavigationLink
                href={selectedPath}
                label={selected?.name ?? "Company Explorer"}
                icon={Building2}
                active={isCompanyPage && !hash.includes("canonical-models")}
                onNavigate={onNavigate}
              />
              <NavigationLink
                href={`${selectedPath}#canonical-models`}
                label="Modeling"
                icon={Settings2}
                active={isCompanyPage && hash.includes("canonical-models")}
                onNavigate={onNavigate}
              />
            </>
          ) : (
            <Link
              href="/universe"
              onClick={onNavigate}
              className="flex min-h-10 items-center gap-2.5 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-sidebar-accent/70 focus-visible:outline-2 focus-visible:outline-ring"
            >
              <Building2 aria-hidden="true" className="size-4 shrink-0" />
              <span>Find a company</span>
            </Link>
          )}
        </NavigationGroup>
        <NavigationGroup title="Operations">
          <NavigationLink
            href="/operations"
            label="Operations status"
            icon={Settings2}
            active={pathname.startsWith("/operations")}
            onNavigate={onNavigate}
          />
        </NavigationGroup>
      </div>
    );
  }

  return (
    <>
      <nav
        aria-label="Main navigation"
        className="hidden min-w-0 flex-1 flex-col md:flex"
      >
        {links()}
      </nav>
      <div className="flex items-center gap-2 md:hidden">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-expanded={mobileOpen}
          aria-controls="mobile-main-navigation"
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? (
            <PanelLeftClose aria-hidden="true" />
          ) : (
            <Menu aria-hidden="true" />
          )}
          {mobileOpen ? "Close" : "Menu"}
        </Button>
      </div>
      {mobileOpen && (
        <nav
          id="mobile-main-navigation"
          aria-label="Main navigation"
          className="mt-4 max-h-[65vh] overflow-y-auto rounded-lg border bg-sidebar p-3 md:hidden"
        >
          {links(() => setMobileOpen(false))}
        </nav>
      )}
    </>
  );
}

function NavigationGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title}>
      <h2 className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      <div className="space-y-0.5">{children}</div>
    </section>
  );
}
