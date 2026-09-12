import { API_URL } from "../constants/api";
import { useAuthStore } from "./useAuthStore";

export interface ApiResult<T> {
  ok: boolean;
  /** HTTP status code (0 when the request never reached the server). */
  status: number;
  data?: T;
  /** Backend `detail`, when it is a plain message string. */
  detail?: string;
  /** Raw `detail` value, for errors whose detail is a structured object
   * (e.g. the 409 of `POST /down-times`). `undefined` when the body carried
   * no `detail` at all. */
  detailBody?: unknown;
}

/** Read the `detail` of a non-2xx JSON body. Returns the raw value plus, when
 * it is a string, the message every caller already renders. */
async function readErrorDetail(
  res: Response,
): Promise<{ detail?: string; detailBody?: unknown }> {
  try {
    const err = (await res.json()) as { detail?: unknown };
    const detailBody = err?.detail;
    return {
      detail: typeof detailBody === "string" ? detailBody : undefined,
      detailBody,
    };
  } catch {
    // no JSON body
    return {};
  }
}

/** Authenticated JSON request: adds the bearer token from the auth store and
 * unwraps the ApiResponse envelope's `data`. Used for all post-login calls. */
export async function apiRequest<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE" = "GET",
  body?: unknown,
): Promise<ApiResult<T>> {
  try {
    const token = useAuthStore.getState().token;
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (res.ok) {
      let data: T | undefined;
      try {
        const json = (await res.json()) as { data: T };
        data = json.data;
      } catch {
        // some endpoints may return an empty body
      }
      return { ok: true, status: res.status, data };
    }
    return { ok: false, status: res.status, ...(await readErrorDetail(res)) };
  } catch {
    return { ok: false, status: 0 };
  }
}

/** POST JSON to the API, unwrapping the ApiResponse envelope's `data`. */
export async function postJson<T>(
  path: string,
  body: unknown,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const json = (await res.json()) as { data: T };
      return { ok: true, status: res.status, data: json.data };
    }
    return { ok: false, status: res.status, ...(await readErrorDetail(res)) };
  } catch {
    return { ok: false, status: 0 };
  }
}
