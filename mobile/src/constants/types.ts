/** Authenticated user returned by the backend auth endpoints
 * (mirrors the backend AuthUserOut contract). */
export interface AuthUser {
  id: string;
  email: string | null;
  first_name: string;
  last_name: string;
  role: string;
  namespace_id: string;
  avatar_url?: string | null;
}

/** Successful login payload (mirrors the backend LoginOut contract). */
export interface LoginData {
  access_token: string;
  token_type: string;
  user: AuthUser;
}
