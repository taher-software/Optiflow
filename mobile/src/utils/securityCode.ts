/** Alphabet the backend generates security codes from: digits plus uppercase
 * letters, minus the ones that read alike on a shop-floor label (I, L, O, U).
 * Digits are part of it, so legacy 4-digit codes stay valid. */
export const SECURITY_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

/** Length of a security code, legacy and current alike. */
export const SECURITY_CODE_LENGTH = 4;

/** Normalize raw keyboard input into what a code can look like: uppercase,
 * alphanumeric only, capped at the code length. Excluded letters are kept
 * here on purpose so `isSecurityCode` can explain the rejection rather than
 * having characters vanish under the user's thumb. */
export function normalizeSecurityCode(input: string): string {
  return input
    .toUpperCase()
    .replace(/[^0-9A-Z]/g, "")
    .slice(0, SECURITY_CODE_LENGTH);
}

/** Whether `value` is a well-formed security code (right length, alphabet). */
export function isSecurityCode(value: string): boolean {
  if (value.length !== SECURITY_CODE_LENGTH) return false;
  return [...value].every((char) => SECURITY_CODE_ALPHABET.includes(char));
}
