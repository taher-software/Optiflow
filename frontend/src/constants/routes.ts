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
} as const;
