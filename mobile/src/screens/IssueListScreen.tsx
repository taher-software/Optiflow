import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { FlatList, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  formatDuration,
  slug,
  STATUS_META,
  type DownTime,
} from "../constants/downtime";
import type { RootStackParamList } from "../constants/routes";
import { useDownTimeStore } from "../stores/useDownTimeStore";
import { useFocusRefresh } from "../utils/useFocusRefresh";

type Props = NativeStackScreenProps<RootStackParamList, "IssueList">;

/** Lists the downtime issues in a given status; tap an issue for its detail. */
export function IssueListScreen({ route, navigation }: Props) {
  const { status } = route.params;
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const issues = useDownTimeStore((s) => s.issues);
  const loading = useDownTimeStore((s) => s.loadingIssues);
  const fetchIssues = useDownTimeStore((s) => s.fetchIssues);

  useFocusRefresh(
    useCallback(() => {
      void fetchIssues(status);
    }, [fetchIssues, status]),
  );

  return (
    <View
      className="flex-1 bg-slate-950"
      style={{ paddingTop: insets.top + 8 }}
    >
      <View className="flex-row items-center gap-3 px-5 py-3">
        <Pressable
          onPress={() => navigation.goBack()}
          accessibilityRole="button"
          hitSlop={12}
        >
          <Text className="text-2xl text-slate-300">‹</Text>
        </Pressable>
        <Text className="text-xl font-bold text-white">
          {STATUS_META[status].emoji} {t(`downtime.status.${status}`)}
        </Text>
      </View>

      <FlatList
        data={issues}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{
          paddingHorizontal: 20,
          paddingBottom: insets.bottom + 24,
        }}
        refreshing={loading}
        onRefresh={() => void fetchIssues(status)}
        ListEmptyComponent={
          loading ? null : (
            <Text className="mt-10 text-center text-sm text-slate-400">
              {t("downtime.list.empty")}
            </Text>
          )
        }
        renderItem={({ item }) => (
          <IssueRow
            issue={item}
            onPress={() => navigation.navigate("IssueDetail", { id: item.id })}
          />
        )}
      />
    </View>
  );
}

function IssueRow({
  issue,
  onPress,
}: {
  issue: DownTime;
  onPress: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      className="mb-3 rounded-2xl border border-slate-800 bg-slate-900 p-4"
    >
      <View className="flex-row items-start justify-between gap-2">
        <Text className="flex-1 text-base font-semibold text-white">
          {t(`downtime.type.${slug(issue.down_time_type)}`)}
        </Text>
        <View
          className="rounded-lg px-2 py-1"
          style={{ backgroundColor: STATUS_META[issue.status].color + "22" }}
        >
          <Text
            className="text-xs font-medium"
            style={{ color: STATUS_META[issue.status].color }}
          >
            {t(`downtime.status.${issue.status}`)}
          </Text>
        </View>
      </View>
      <Text className="mt-2 text-xs text-slate-400">
        {t(`downtime.process.${issue.process}`)} ·{" "}
        {t("downtime.list.inStatus", {
          time: formatDuration(issue.time_in_status_seconds),
        })}
      </Text>
    </Pressable>
  );
}

export default IssueListScreen;
