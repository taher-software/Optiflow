/** A production line as returned by the API. */
export interface ProductionLine {
  id: string;
  name: string;
  description: string;
  /** The zone area (production area / UAP) this line belongs to. */
  uap_id: string;
  namespace_id: string;
}

export interface CreateProductionLinePayload {
  name: string;
  description: string;
  uap_id: string;
}

export type UpdateProductionLinePayload = Partial<CreateProductionLinePayload>;
