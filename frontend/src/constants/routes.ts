/** Canonical app route paths. */
export const ROUTES = {
  /** Public marketing / prospect landing page. */
  prospect: "/",
  /** Sign-in page. */
  login: "/login",
  /** Account registration (create a new namespace). */
  register: "/register",
  /** Email/account confirmation landing (reads ?token=). */
  confirmAccount: "/confirm-account",
  /** Privacy policy (public; the URL declared to the app stores). */
  privacy: "/privacy",
  /** Terms of sale — Conditions générales de vente (public). */
  terms: "/terms",
  /** Protected operations area (tenant-scoped). */
  app: "/app",
  /** User management (owner/admin). */
  users: "/app/users",
  /** New-user form. */
  newUser: "/app/users/new",
  /** Production areas (owner/admin/production-supervisor). */
  uaps: "/app/uaps",
  /** New production-area form. */
  newUap: "/app/uaps/new",
  /** Production lines. */
  lines: "/app/production-lines",
  /** New production-line form. */
  newLine: "/app/production-lines/new",
  /** Work stations. */
  stations: "/app/workstations",
  /** New workstation form. */
  newStation: "/app/workstations/new",
  /** Namespace plant settings (shifts + escalation delay). */
  settings: "/app/settings",
  /** Day-scoped downtime gantt (owner/admin/manager/production-supervisor). */
  downTimes: "/app/down-times",
  /** Stats explorer (daily KPI tracking + episode comparison). */
  stats: "/app/stats",
  /** Subscription paywall: plans, amounts and bank transfer instructions
   * (only reachable when the subscription is expired or blocked). */
  subscription: "/app/subscription",
} as const;
