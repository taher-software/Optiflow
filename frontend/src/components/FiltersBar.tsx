import type { ReactNode } from "react";

interface FiltersBarProps {
  children: ReactNode;
}

/** Responsive row holding a list page's search and filter controls. */
export function FiltersBar({ children }: FiltersBarProps) {
  return (
    <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {children}
    </div>
  );
}
