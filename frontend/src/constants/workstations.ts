/** A workstation as returned by the API. */
export interface Workstation {
  id: string;
  name: string;
  description: string;
  /** The production line this station belongs to, or null when independent. */
  production_line_id: string | null;
  type: string;
  namespace_id: string;
}

export interface CreateWorkstationPayload {
  name: string;
  description: string;
  production_line_id: string | null;
  type: string;
}

export type UpdateWorkstationPayload = Partial<CreateWorkstationPayload>;

/** Workstation type values (mirror the backend WorkstationType enum). */
export const WORKSTATION_TYPES = [
  "standard",
  "bottleneck",
  "critical",
] as const;
