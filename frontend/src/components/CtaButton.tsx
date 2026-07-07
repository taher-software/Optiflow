import type { ReactNode } from "react";

interface CtaButtonProps {
  children: ReactNode;
  href?: string;
  variant?: "primary" | "ghost";
  /** Open in a new tab (for external links such as Calendly). */
  external?: boolean;
}

/** Marketing call-to-action link, styled as a button. Presentational. */
export function CtaButton({
  children,
  href = "#",
  variant = "primary",
  external = false,
}: CtaButtonProps) {
  const base =
    "inline-flex items-center justify-center rounded-xl px-6 py-3 text-sm font-semibold transition-colors";
  const styles =
    variant === "primary"
      ? "bg-teal-400 text-slate-950 hover:bg-teal-300"
      : "border border-slate-700 text-slate-200 hover:border-slate-500 hover:text-white";

  const externalProps = external
    ? { target: "_blank", rel: "noopener noreferrer" }
    : {};

  return (
    <a href={href} className={`${base} ${styles}`} {...externalProps}>
      {children}
    </a>
  );
}
