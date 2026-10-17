import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type ResponsiveColumn<T> = {
  id: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
};

export function ResponsiveDataTable<T>({
  caption,
  columns,
  rows,
  getRowKey,
  className,
}: {
  caption: string;
  columns: ResponsiveColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="hidden overflow-hidden rounded-lg border md:block">
        <table className="w-full table-fixed text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-muted/70 text-xs text-muted-foreground">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  className={cn("px-3 py-2.5 font-medium", column.className)}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => (
              <tr key={getRowKey(row)} className="align-top">
                {columns.map((column) => (
                  <td
                    key={column.id}
                    className={cn("break-words px-3 py-3", column.className)}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div
        className="space-y-2 md:hidden"
        aria-label={`${caption}, mobile view`}
      >
        {rows.map((row) => (
          <dl
            key={getRowKey(row)}
            className="grid min-w-0 grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-x-3 gap-y-2 rounded-lg border bg-card p-3 text-sm"
          >
            {columns.map((column) => (
              <div key={column.id} className="contents">
                <dt className="min-w-0 break-words text-xs text-muted-foreground">
                  {column.header}
                </dt>
                <dd className="min-w-0 break-words text-right">
                  {column.render(row)}
                </dd>
              </div>
            ))}
          </dl>
        ))}
      </div>
      {rows.length === 0 && (
        <p className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
          No rows available for {caption.toLowerCase()}.
        </p>
      )}
    </div>
  );
}
