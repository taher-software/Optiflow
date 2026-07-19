import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BrandLogo } from "../components/BrandLogo";
import type { RootStackParamList } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";
import { useDeviceStore } from "../stores/useDeviceStore";
import { useToastStore } from "../stores/useToastStore";

type Props = NativeStackScreenProps<RootStackParamList, "SecurityCode">;

/** Pairing screen: the user enters their 4-digit security code to bind this
 * device. On success the device id is cached and the app opens. */
export function SecurityCodeScreen({ navigation }: Props) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const checkUserCode = useAuthStore((s) => s.checkUserCode);
  const persist = useDeviceStore((s) => s.persist);
  const showToast = useToastStore((s) => s.show);

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const onSave = async () => {
    const value = code.trim();
    if (value.length !== 4) {
      showToast(t("securityCode.invalid"));
      return;
    }
    setBusy(true);
    try {
      const res = await checkUserCode(value);
      if (res.ok) {
        await persist();
        navigation.replace("Home");
      } else if (res.status === 404) {
        showToast(t("errors.codeNotFound"));
      } else {
        showToast(res.status === 0 ? t("errors.network") : t("errors.generic"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <View
      className="flex-1 bg-slate-950 px-6"
      style={{ paddingTop: insets.top + 48, paddingBottom: insets.bottom + 16 }}
    >
      <BrandLogo />

      <Text className="mt-12 text-2xl font-bold tracking-tight text-white">
        {t("securityCode.title")}
      </Text>
      <Text className="mt-2 text-sm leading-relaxed text-slate-400">
        {t("securityCode.subtitle")}
      </Text>

      <Text className="mb-2 mt-8 text-sm font-medium text-slate-300">
        {t("securityCode.label")}
      </Text>
      <TextInput
        value={code}
        onChangeText={(v) => setCode(v.replace(/[^0-9]/g, "").slice(0, 4))}
        keyboardType="number-pad"
        maxLength={4}
        autoFocus
        accessibilityLabel={t("securityCode.label")}
        placeholder="••••"
        placeholderTextColor="#475569"
        className="rounded-2xl border border-slate-700 bg-slate-900 px-4 py-4 text-center text-2xl tracking-[16px] text-white"
      />

      <Pressable
        onPress={onSave}
        disabled={busy}
        accessibilityRole="button"
        className={`mt-8 h-14 flex-row items-center justify-center rounded-2xl bg-teal-400 ${
          busy ? "opacity-60" : ""
        }`}
      >
        {busy ? (
          <ActivityIndicator color="#020617" />
        ) : (
          <Text className="text-base font-semibold text-slate-950">
            {t("securityCode.save")}
          </Text>
        )}
      </Pressable>
    </View>
  );
}

export default SecurityCodeScreen;
