/** A production line as returned by the API. */
export interface ProductionLine {
  id: string;
  name: string;
  description: string;
  /** The zone area (production area / UAP) this line belongs to, or null when
   * the line is independent of any zone area. */
  uap_id: string | null;
  namespace_id: string;
}

export interface CreateProductionLinePayload {
  name: string;
  description: string;
  /** `null` detaches the line from its zone area. Always send the key
   * explicitly: the API treats an omitted key as "leave untouched". */
  uap_id: string | null;
}

export type UpdateProductionLinePayload = Partial<CreateProductionLinePayload>;
