import * as Device from "expo-device";
import * as Notifications from "expo-notifications";

/**
 * Resolve this device's Expo push token, requesting notification permission if
 * needed. Returns `null` when unavailable (simulator, web, denied permission,
 * or missing push config) so callers can proceed without a token.
 */
export async function getPushToken(): Promise<string | null> {
  try {
    if (!Device.isDevice) return null;

    const existing = await Notifications.getPermissionsAsync();
    let granted = existing.granted;
    if (!granted && existing.canAskAgain) {
      const requested = await Notifications.requestPermissionsAsync();
      granted = requested.granted;
    }
    if (!granted) return null;

    const token = await Notifications.getExpoPushTokenAsync();
    return token.data;
  } catch {
    return null;
  }
}
