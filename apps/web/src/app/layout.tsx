import type { Metadata } from "next";
import { Layers2, Palette } from "lucide-react";
import Link from "next/link";

import "./globals.css";
import { ContextHeader } from "@/components/app/context-header";
import { Navigation } from "@/components/app/navigation";

export const metadata: Metadata = {
  title: "Portfolio Research · Portfolio",
  description:
    "An equity research and portfolio management workspace for long-term ownership.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <div className="min-h-screen md:grid md:grid-cols-[var(--app-sidebar-width)_1fr]">
          <aside className="flex flex-col border-b bg-sidebar px-4 py-4 sm:px-5 md:min-h-screen md:border-r md:border-b-0 md:px-5 md:py-7">
            <Link
              href="/"
              aria-label="Portfolio home"
              className="flex w-fit items-center gap-2.5 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
            >
              <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Layers2 aria-hidden="true" className="size-4" />
              </span>
              <span className="text-lg font-semibold tracking-tight">
                Portfolio<span className="text-primary">.</span>
              </span>
            </Link>
            <div className="mt-4 md:mt-9">
              <Navigation />
            </div>
            {process.env.NODE_ENV === "development" && (
              <Link
                href="/design-system"
                className="mt-2 flex w-fit items-center gap-2 rounded-md px-3 py-2 text-xs text-muted-foreground hover:bg-sidebar-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <Palette aria-hidden="true" className="size-3.5" />
                Design system reference
              </Link>
            )}
            <div className="mt-auto hidden pt-12 md:block">
              <div className="mb-3 h-px w-8 bg-border" />
              <p className="text-xs font-medium">Built for the long term.</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Equity research &amp;
                <br />
                portfolio management
              </p>
            </div>
          </aside>
          <div className="min-w-0">
            <header className="flex min-h-16 items-center gap-4 border-b px-4 py-3 sm:px-6 md:px-10">
              <ContextHeader />
              <span className="hidden shrink-0 items-center gap-2 text-xs text-muted-foreground lg:flex">
                <span className="size-1.5 rounded-full bg-muted-foreground/50" />
                Local development
              </span>
            </header>
            <main
              id="main-content"
              tabIndex={-1}
              className="app-main outline-none"
            >
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
