import type { Metadata } from "next";
import { Layers2 } from "lucide-react";
import Link from "next/link";

import "./globals.css";
import { Navigation } from "@/components/navigation";

export const metadata: Metadata = {
  title: "Workspace · Portfolio",
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
        <div className="min-h-screen md:grid md:grid-cols-[224px_1fr]">
          <aside className="flex flex-col border-b bg-sidebar px-5 py-5 md:min-h-screen md:border-r md:border-b-0 md:py-7">
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
            <Navigation />
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
            <header className="flex h-16 items-center justify-between gap-4 border-b px-5 md:px-10">
              <span className="text-xs text-muted-foreground">
                Research workspace
              </span>
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="size-1.5 rounded-full bg-muted-foreground/50" />
                Local development
              </span>
            </header>
            <main
              id="main-content"
              tabIndex={-1}
              className="mx-auto max-w-7xl px-5 py-9 outline-none md:px-10 md:py-12"
            >
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
