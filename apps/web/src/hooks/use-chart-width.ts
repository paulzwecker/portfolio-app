"use client";

import { useEffect, useState } from "react";

/** Match SVG coordinates to rendered width so axis text stays readable on mobile. */
export function useChartWidth(padding = 0, initialWidth = 760) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(initialWidth);
  useEffect(() => {
    if (!container) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(280, entry.contentRect.width - padding)),
    );
    observer.observe(container);
    return () => observer.disconnect();
  }, [container, padding]);
  return { containerRef: setContainer, width };
}
