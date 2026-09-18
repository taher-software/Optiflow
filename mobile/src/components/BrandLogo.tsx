import { View, Text } from "react-native";

import { BRAND } from "../constants/brand";

/** Operio logo mark + wordmark. Presentational, no state. */
export function BrandLogo() {
  return (
    <View className="flex-row items-center gap-3">
      <View className="h-12 w-12 items-center justify-center rounded-2xl bg-teal-400">
        {/* Simple geometric mark (no SVG dependency). */}
        <View className="h-5 w-5 rounded-md border-[3px] border-slate-900" />
      </View>
      <Text className="text-3xl font-bold tracking-tight text-white">
        {BRAND.nameLead}
        <Text className="text-teal-400">{BRAND.nameAccent}</Text>
      </Text>
    </View>
  );
}
