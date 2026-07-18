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
} as const;
