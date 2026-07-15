/** Step 1 — company (namespace) fields. Mirrors the backend CompanyIn contract. */
export interface CompanyForm {
  company_name: string;
  adress: string;
  code_postal: string;
  phone_number: string;
  tax_identification_number: string;
  country: string;
  city: string;
}

/** Step 2 — owner user fields. Mirrors the backend OwnerIn contract. */
export interface OwnerForm {
  firstname: string;
  lastname: string;
  email: string;
  avatar_url?: string;
}

export interface RegisterPayload {
  company: CompanyForm;
  owner: OwnerForm;
}

export const EMPTY_COMPANY: CompanyForm = {
  company_name: "",
  adress: "",
  code_postal: "",
  phone_number: "",
  tax_identification_number: "",
  country: "",
  city: "",
};

export const EMPTY_OWNER: OwnerForm = {
  firstname: "",
  lastname: "",
  email: "",
};
