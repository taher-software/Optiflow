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
  /** Reachability for team push notifications. A user document without the
   * field counts as online, so the backend defaults this to `true`. */
  online: boolean;
}

/** Successful login payload (mirrors the backend LoginOut contract). */
export interface LoginData {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

/** Payload returned by `PATCH /users/me/online`. The backend responds with the
 * full `UserOut`; only `online` is consumed on mobile. */
export interface SetOnlineData {
  online: boolean;
}
