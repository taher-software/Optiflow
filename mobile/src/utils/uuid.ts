import * as Crypto from "expo-crypto";

/** Generate a fresh, unique device id (RFC-4122 UUID v4). */
export function generateDeviceId(): string {
  return Crypto.randomUUID();
}
