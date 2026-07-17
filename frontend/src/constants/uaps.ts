/** A production area (UAP) as returned by the API. */
export interface Uap {
  id: string;
  name: string;
  description: string;
  namespace_id: string;
  maintenance_agent_ids: string[];
  production_agent_ids: string[];
  quality_agent_ids: string[];
  logistic_agent_ids: string[];
  logistic_supervisor_ids: string[];
  maintenance_supervisor_ids: string[];
  quality_supervisor_ids: string[];
  production_supervisor_ids: string[];
}

/** The eight id-list fields that hold a UAP's assigned resources. */
export type UapMemberField =
  | "maintenance_agent_ids"
  | "production_agent_ids"
  | "quality_agent_ids"
  | "logistic_agent_ids"
  | "logistic_supervisor_ids"
  | "maintenance_supervisor_ids"
  | "quality_supervisor_ids"
  | "production_supervisor_ids";

/** Full create payload (name + description + every member list). */
export interface CreateUapPayload {
  name: string;
  description: string;
  maintenance_agent_ids: string[];
  production_agent_ids: string[];
  quality_agent_ids: string[];
  logistic_agent_ids: string[];
  logistic_supervisor_ids: string[];
  maintenance_supervisor_ids: string[];
  quality_supervisor_ids: string[];
  production_supervisor_ids: string[];
}

/** Partial update payload. */
export type UpdateUapPayload = Partial<CreateUapPayload>;

/** The member groups shown in the form: each id-list field maps to the role
 * whose users may fill it. Order drives the UI. */
export const UAP_MEMBER_GROUPS: { field: UapMemberField; role: string }[] = [
  { field: "production_supervisor_ids", role: "production supervisor" },
  { field: "production_agent_ids", role: "production agent" },
  { field: "maintenance_supervisor_ids", role: "maintenance supervisor" },
  { field: "maintenance_agent_ids", role: "maintenance agent" },
  { field: "quality_supervisor_ids", role: "quality supervisor" },
  { field: "quality_agent_ids", role: "quality agent" },
  { field: "logistic_supervisor_ids", role: "logistic supervisor" },
  { field: "logistic_agent_ids", role: "logistic agent" },
];

/** Empty member lists — a helper for initializing form state. */
export function emptyMembers(): Record<UapMemberField, string[]> {
  return {
    maintenance_agent_ids: [],
    production_agent_ids: [],
    quality_agent_ids: [],
    logistic_agent_ids: [],
    logistic_supervisor_ids: [],
    maintenance_supervisor_ids: [],
    quality_supervisor_ids: [],
    production_supervisor_ids: [],
  };
}

/** Total number of assigned resources across every group. */
export function memberCount(uap: Uap): number {
  return UAP_MEMBER_GROUPS.reduce(
    (sum, g) => sum + (uap[g.field]?.length ?? 0),
    0,
  );
}
