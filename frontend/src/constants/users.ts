export interface User {
  id: string;
  first_name: string;
  last_name: string;
  role: string;
  email: string | null;
  security_code: string;
  namespace_id: string;
}

export interface CreateUserPayload {
  first_name: string;
  last_name: string;
  role: string;
  email?: string;
  /** Required only when an email is set. A user without an email signs in from
   * the mobile app with their security code, so no password is needed. */
  password?: string;
}

export type UpdateUserPayload = {
  first_name?: string;
  last_name?: string;
  role?: string;
  email?: string;
  password?: string;
};

/** Roles an owner/admin may assign (everything except owner). */
export const ASSIGNABLE_ROLES = [
  "admin",
  "manager",
  "production supervisor",
  "production agent",
  "quality supervisor",
  "quality agent",
  "maintenance supervisor",
  "maintenance agent",
  "logistic supervisor",
  "logistic agent",
] as const;

/** i18n-safe key slug for a role value ("quality agent" -> "quality_agent"). */
export function roleSlug(role: string): string {
  return role.replace(/ /g, "_");
}

/** Email is required for admin, manager, and any supervisor role. */
export function roleNeedsEmail(role: string): boolean {
  return role === "admin" || role === "manager" || role.endsWith("supervisor");
}
