/**
 * The 409 `detail` of `POST /down-times` when the target, or one of its
 * ancestors, already has an open downtime (`down_time/services.py::
 * _conflict_detail`, spec §4). The backend writes the user-facing sentence in
 * both supported languages, so the app shows it as-is.
 */
interface ConflictDetailBody {
  message_fr?: unknown;
  message_en?: unknown;
}

function nonBlank(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/**
 * The backend's conflict sentence in `language` (the app language, which
 * follows the device), falling back to the other language when that version
 * is missing. `null` when the body carries neither — an older backend, or a
 * proxy that rewrote the error — so the caller can show its own message.
 * `detail` is typed `unknown` on purpose: it is whatever the error body held.
 */
export function conflictMessage(
  detail: unknown,
  language: string,
): string | null {
  if (typeof detail !== "object" || detail === null) return null;
  const body = detail as ConflictDetailBody;
  const fr = nonBlank(body.message_fr);
  const en = nonBlank(body.message_en);
  return language === "fr" ? (fr ?? en) : (en ?? fr);
}
