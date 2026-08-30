import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { BrandLogo } from "../components/BrandLogo";
import { OnlineToggle } from "../components/OnlineToggle";
import {
  DOWN_TIME_STATUSES,
  formatDuration,
  STATUS_META,
  type DownTimeStatus,
} from "../constants/downtime";
import type { RootStackParamList } from "../constants/routes";
import { useAuthStore } from "../stores/useAuthStore";
import { useDownTimeStore } from "../stores/useDownTimeStore";
import { useFocusRefresh } from "../utils/useFocusRefresh";

type Props = NativeStackScreenProps<RootStackParamList, "Home">;

/** Home dashboard: the four downtime status cards + (for production agents) a
 * declare-downtime action. */
export function HomeScreen({ navigation }: Props) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const user = useAuthStore((s) => s.user);
  const settingOnline = useAuthStore((s) => s.settingOnline);
  const setOnline = useAuthStore((s) => s.setOnline);
  const summary = useDownTimeStore((s) => s.summary);
  const loading = useDownTimeStore((s) => s.loadingSummary);
  const fetchSummary = useDownTimeStore((s) => s.fetchSummary);

  useFocusRefresh(
    useCallback(() => {
      void fetchSummary();
    }, [fetchSummary]),
  );

  const isProductionAgent = user?.role === "production agent";

  return (
    <ScrollView
      className="flex-1 bg-slate-950"
      contentContainerStyle={{
        paddingTop: insets.top + 24,
        paddingBottom: insets.bottom + 24,
        paddingHorizontal: 20,
      }}
      refreshControl={
        <RefreshControl
          refreshing={loading}
          onRefresh={() => void fetchSummary()}
          tintColor="#2dd4bf"
        />
      }
    >
      <BrandLogo />
      <Text className="mt-8 text-2xl font-bold tracking-tight text-white">
        {t("home.greeting")}
        {user ? `, ${user.first_name}` : ""}.
      </Text>
      <Text className="mt-1 text-sm text-slate-400">{t("home.overview")}</Text>

      {user && (
        <OnlineToggle
          online={user.online}
          pending={settingOnline}
          onChange={(next) => void setOnline(next)}
        />
      )}

      <View className="mt-6 flex-row flex-wrap justify-between">
        {DOWN_TIME_STATUSES.map((status) => (
          <StatusCard
            key={status}
            status={status}
            count={summary ? summary[status].count : 0}
            averageSeconds={summary ? summary[status].average_seconds : null}
            onPress={() => navigation.navigate("IssueList", { status })}
          />
        ))}
      </View>

      {isProductionAgent && (
        <Pressable
          onPress={() => navigation.navigate("DeclareDownTime")}
          accessibilityRole="button"
          className="mt-4 h-14 flex-row items-center justify-center gap-2 rounded-2xl bg-teal-400"
        >
          <Text className="text-lg">🚨</Text>
          <Text className="text-base font-semibold text-slate-950">
            {t("home.declare")}
          </Text>
        </Pressable>
      )}
    </ScrollView>
  );
}

interface StatusCardProps {
  status: DownTimeStatus;
  count: number;
  averageSeconds: number | null;
  onPress: () => void;
}

function StatusCard({
  status,
  count,
  averageSeconds,
  onPress,
}: StatusCardProps) {
  const { t } = useTranslation();
  const meta = STATUS_META[status];
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      className="mb-4 w-[48%] rounded-2xl border border-slate-800 bg-slate-900 p-4"
    >
      <View className="flex-row items-center justify-between">
        <Text className="text-2xl">{meta.emoji}</Text>
        <Text className="text-3xl font-bold" style={{ color: meta.color }}>
          {count}
        </Text>
      </View>
      <Text className="mt-3 text-sm font-semibold text-white">
        {t(`downtime.status.${status}`)}
      </Text>
      <Text className="mt-1 text-xs text-slate-400">
        {t("downtime.avgTime")}: {formatDuration(averageSeconds)}
      </Text>
    </Pressable>
  );
}

export default HomeScreen;
