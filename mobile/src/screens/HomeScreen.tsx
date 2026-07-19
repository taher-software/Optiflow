import { useTranslation } from "react-i18next";
import { Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BrandLogo } from "../components/BrandLogo";
import { useAuthStore } from "../stores/useAuthStore";

/** Home screen shown once the device is authenticated. */
export function HomeScreen() {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const user = useAuthStore((s) => s.user);

  return (
    <View
      className="flex-1 bg-slate-950 px-6"
      style={{ paddingTop: insets.top + 48 }}
    >
      <BrandLogo />
      <Text className="mt-12 text-2xl font-bold tracking-tight text-white">
        {t("home.greeting")}
        {user ? `, ${user.first_name}` : ""}.
      </Text>
      <Text className="mt-2 text-sm leading-relaxed text-slate-400">
        {t("home.subtitle")}
      </Text>
    </View>
  );
}

export default HomeScreen;
