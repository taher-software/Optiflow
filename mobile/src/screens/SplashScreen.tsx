import { View, Text, ActivityIndicator } from "react-native";

import { BrandLogo } from "../components/BrandLogo";
import { BRAND, ACCENT_COLOR } from "../constants/brand";

/**
 * Splash / launch screen shown while the mobile app boots
 * (session check, tenant resolution, initial data).
 * Presentational only — no data fetching.
 */
export function SplashScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-slate-950 px-6">
      <BrandLogo />
      <Text className="mt-5 max-w-xs text-center text-sm font-medium text-slate-400">
        {BRAND.tagline}
      </Text>
      <ActivityIndicator className="mt-12" color={ACCENT_COLOR} />
    </View>
  );
}

export default SplashScreen;
