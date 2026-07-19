import { API_URL } from "../constants/api";

export interface ApiResult<T> {
  ok: boolean;
  /** HTTP status code (0 when the request never reached the server). */
  status: number;
  data?: T;
  /** Backend `detail` message, if any. */
  detail?: string;
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
    let detail: string | undefined;
    try {
      const err = (await res.json()) as { detail?: string };
      detail = err.detail;
    } catch {
      // no JSON body
    }
    return { ok: false, status: res.status, detail };
  } catch {
    return { ok: false, status: 0 };
  }
}
