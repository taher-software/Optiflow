import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

/**
 * Register the Android notification channels the backend targets by
 * `channelId`. On Android 8+ the sound is a property of the channel (not the
 * push payload), so each level's custom sound is bound here; the filenames
 * must match the bundled `assets/sounds/*.wav` (see `expo-notifications`
 * `sounds` in app.json). No-op on iOS, which uses the payload `sound` field.
 */
export async function registerNotificationChannels(): Promise<void> {
  if (Platform.OS !== "android") return;
  await Notifications.setNotificationChannelAsync("urgent", {
    name: "Urgent",
    importance: Notifications.AndroidImportance.MAX,
    sound: "urgent.wav",
    vibrationPattern: [0, 250, 250, 250],
  });
  await Notifications.setNotificationChannelAsync("standard", {
    name: "Standard",
    importance: Notifications.AndroidImportance.DEFAULT,
    sound: "standard.wav",
  });
}

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

    // Channels must exist before notifications arrive so the custom sound
    // plays; register them as soon as permission is in hand.
    await registerNotificationChannels();

    const token = await Notifications.getExpoPushTokenAsync();
    return token.data;
  } catch {
    return null;
  }
}
