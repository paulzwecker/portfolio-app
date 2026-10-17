import { BookOpen, ArrowUpRight } from "lucide-react";

import { ServiceStatus } from "@/components/app/service-status";
import { PageHeader } from "@/components/app/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import Link from "next/link";

export default function Home() {
  return (
    <>
      <PageHeader
        eyebrow="A long-term perspective"
        title="Overview"
        description="A considered view of the businesses you own, and the ones worth studying."
      />
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
        <Card className="overflow-hidden shadow-none">
          <div className="flex items-center justify-between gap-3 border-b px-6 py-4">
            <h2 className="text-sm font-medium">Overview</h2>
            <Badge variant="secondary" className="font-normal">
              Research foundation
            </Badge>
          </div>
          <CardContent className="flex min-h-80 flex-col items-center justify-center px-6 py-14 text-center sm:min-h-96">
            <div className="mb-6 flex size-14 items-center justify-center rounded-2xl border bg-secondary/60">
              <BookOpen
                aria-hidden="true"
                className="size-6 text-primary"
                strokeWidth={1.4}
              />
            </div>
            <h2 className="text-xl font-medium tracking-tight">
              A foundation for thoughtful ownership
            </h2>
            <p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground">
              Explore observed holdings, strategic targets and the companies in
              your research universe.
            </p>
            <div className="mt-7 inline-flex items-center gap-2 text-xs text-muted-foreground">
              <ArrowUpRight aria-hidden="true" className="size-3.5" />
              <Link href="/portfolio" className="underline underline-offset-4">
                Open portfolio
              </Link>
              <Link href="/universe" className="underline underline-offset-4">
                Explore universe
              </Link>
            </div>
          </CardContent>
          <p className="border-t bg-secondary/30 px-6 py-4 text-xs leading-5 text-muted-foreground">
            Financial outputs will appear as source data and models are
            verified. Demonstration data, when seeded, is labeled on the domain
            pages.
          </p>
        </Card>
        <ServiceStatus />
      </div>
      <footer className="mt-8 text-xs leading-5 text-muted-foreground">
        Quality first. Explicit assumptions. Traceable decisions.
      </footer>
    </>
  );
}
