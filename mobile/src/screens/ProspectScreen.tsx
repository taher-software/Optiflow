import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BrandLogo } from "../components/BrandLogo";
import { ACCENT_COLOR } from "../constants/brand";
import type { RootStackParamList } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";
import { useDeviceStore } from "../stores/useDeviceStore";
import { useToastStore } from "../stores/useToastStore";

type Props = NativeStackScreenProps<RootStackParamList, "Prospect">;

/** Landing/prospect screen. Presents the product and, on mount, runs the device
 * flow automatically: a cached device silently logs in; a new device goes to
 * pairing. A loader shows until the redirect happens. */
export function ProspectScreen({ navigation }: Props) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const bootstrap = useDeviceStore((s) => s.bootstrap);
  const generate = useDeviceStore((s) => s.generate);
  const mobileLogin = useAuthStore((s) => s.mobileLogin);
  const showToast = useToastStore((s) => s.show);
  const [failed, setFailed] = useState(false);
  const running = useRef(false);

  const values = [
    t("prospect.values.visibility"),
    t("prospect.values.response"),
    t("prospect.values.improve"),
  ];

  const enter = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    setFailed(false);
    try {
      const cached = await bootstrap();
      if (cached) {
        const res = await mobileLogin();
        if (res.ok) {
          navigation.replace("Home");
        } else if (res.status === 404) {
          // The cached device is no longer paired — pair again.
          generate();
          navigation.replace("SecurityCode");
        } else {
          showToast(
            res.status === 0 ? t("errors.network") : t("errors.generic"),
          );
          setFailed(true);
        }
      } else {
        generate();
        navigation.replace("SecurityCode");
      }
    } finally {
      running.current = false;
    }
  }, [bootstrap, generate, mobileLogin, navigation, showToast, t]);

  useEffect(() => {
    void enter();
  }, [enter]);

  return (
    <View className="flex-1 bg-slate-950">
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + 32,
          paddingBottom: 24,
          paddingHorizontal: 24,
          flexGrow: 1,
        }}
      >
        <BrandLogo />

        <View className="mt-10 self-start rounded-full border border-slate-700 px-3 py-1">
          <Text className="text-xs font-medium text-teal-300">
            {t("prospect.badge")}
          </Text>
        </View>

        <Text className="mt-6 text-4xl font-bold leading-tight tracking-tight text-white">
          {t("prospect.headline")}
        </Text>
        <Text className="mt-4 text-base leading-relaxed text-slate-400">
          {t("prospect.subhead")}
        </Text>

        <View className="mt-8 gap-4">
          {values.map((v) => (
            <View key={v} className="flex-row items-start gap-3">
              <View className="mt-1 h-2 w-2 rounded-full bg-teal-400" />
              <Text className="flex-1 text-sm text-slate-300">{v}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      <View
        className="items-center px-6"
        style={{ paddingBottom: insets.bottom + 24, paddingTop: 8 }}
      >
        {failed ? (
          <Pressable
            onPress={() => void enter()}
            accessibilityRole="button"
            className="flex-row items-center gap-2"
          >
            <Text className="text-sm font-medium text-teal-400">
              {t("prospect.retry")}
            </Text>
          </Pressable>
        ) : (
          <View className="flex-row items-center gap-3">
            <ActivityIndicator color={ACCENT_COLOR} />
            <Text className="text-sm text-slate-400">
              {t("prospect.connecting")}
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}

export default ProspectScreen;
