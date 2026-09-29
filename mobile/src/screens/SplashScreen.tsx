import { View, Text, Image, ActivityIndicator } from "react-native";

import { BRAND, ACCENT_COLOR } from "../constants/brand";

const LOGO = require("../../assets/logo.png");

/**
 * Splash / launch screen shown while the mobile app boots
 * (session check, tenant resolution, initial data).
 * Mirrors the native splash (assets/splash.png) so the hand-off is seamless.
 * Presentational only — no data fetching.
 */
export function SplashScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-slate-950 px-6">
      <Image
        source={LOGO}
        className="h-28 w-28"
        resizeMode="contain"
        accessibilityLabel={BRAND.name}
      />
      <Text className="mt-4 text-4xl font-bold tracking-tight text-white">
        {BRAND.nameLead}
        <Text className="text-teal-400">{BRAND.nameAccent}</Text>
      </Text>
      <Text className="mt-3 max-w-xs text-center text-sm font-medium text-slate-400">
        {BRAND.tagline}
      </Text>
      <ActivityIndicator className="mt-12" color={ACCENT_COLOR} />
    </View>
  );
}

export default SplashScreen;
