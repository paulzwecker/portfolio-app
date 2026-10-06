"use client";

import { Activity, BookOpen, Layers2, PanelLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function Navigation() {
  const pathname = usePathname();
  const items = [
    { href: "/", label: "Workspace", icon: PanelLeft },
    { href: "/portfolio", label: "Portfolio", icon: Layers2 },
    { href: "/attention", label: "Attention", icon: Activity },
    { href: "/universe", label: "Universe", icon: BookOpen },
  ];
  return (
    <nav
      aria-label="Main navigation"
      className="mt-5 flex gap-1 md:mt-10 md:flex-col"
    >
      {items.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/" ? pathname === href : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-ring",
              active && "bg-sidebar-accent font-medium",
            )}
          >
            <Icon aria-hidden="true" className="size-4 text-primary" />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
