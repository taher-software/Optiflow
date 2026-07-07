import type { FeatureIconName } from "../constants/features";

interface FeatureIconProps {
  name: FeatureIconName;
}

/** Small line icons for the prospect-page features. Presentational. */
export function FeatureIcon({ name }: FeatureIconProps) {
  const svg = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "h-6 w-6",
    "aria-hidden": true,
  };

  switch (name) {
    case "automate":
      // lightning / instant automation
      return (
        <svg {...svg}>
          <path d="M13 2L4.1 12.1a1 1 0 0 0 .77 1.65H11l-1 8 8.9-10.1a1 1 0 0 0-.77-1.65H12l1-8z" />
        </svg>
      );
    case "empower":
      // people / staff
      return (
        <svg {...svg}>
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case "transparent":
      // eye / visibility
      return (
        <svg {...svg}>
          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "rootcause":
      // magnifier + plus / find & fix
      return (
        <svg {...svg}>
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
          <path d="M11 8v6" />
          <path d="M8 11h6" />
        </svg>
      );
  }
}
