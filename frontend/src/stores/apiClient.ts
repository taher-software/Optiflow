import { API_URL } from "../constants/api";
import { authHeader } from "./useAuthStore";

export interface Result<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

/** Authenticated JSON request against the API, unwrapping the ApiResponse
 * envelope's `data` on success and the `detail` message on failure. */
export async function request<T>(
  path: string,
  method: string,
  body?: unknown,
): Promise<Result<T>> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.ok) {
      const json = (await res.json()) as { data: T };
      return { ok: true, data: json.data };
    }
    let error = "Une erreur est survenue. Veuillez réessayer.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (data.detail) error = data.detail;
    } catch {
      // no JSON body
    }
    return { ok: false, error };
  } catch {
    return { ok: false, error: "Impossible de contacter le serveur." };
  }
}
