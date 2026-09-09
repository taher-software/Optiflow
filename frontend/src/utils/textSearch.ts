/** Text search helpers for client-side list filtering. Pure, no React. */

/**
 * Lowercases and strips diacritics so that "Rivière" and "riviere" compare
 * equal. Uses NFD normalization plus a Unicode diacritic-mark removal.
 */
export function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/**
 * True when every whitespace-separated token of `query` is found somewhere in
 * the concatenated `fields`. Tokens match independently and in any order, so
 * "mar dup" matches "Marie Dupont". An empty query matches everything.
 */
export function matchesQuery(
  query: string,
  ...fields: (string | null | undefined)[]
): boolean {
  const tokens = normalizeText(query).split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;
  const haystack = normalizeText(
    fields.filter((field): field is string => Boolean(field)).join(" "),
  );
  return tokens.every((token) => haystack.includes(token));
}
