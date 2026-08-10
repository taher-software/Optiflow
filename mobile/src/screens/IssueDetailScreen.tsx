import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  formatDuration,
  isCloseOnly,
  slug,
  STATUS_META,
  type DownTime,
} from "../constants/downtime";
import type { RootStackParamList } from "../constants/routes";
import { useDownTimeStore } from "../stores/useDownTimeStore";
import { useResourcesStore } from "../stores/useResourcesStore";
import { useToastStore } from "../stores/useToastStore";

type Props = NativeStackScreenProps<RootStackParamList, "IssueDetail">;

function humanTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString();
}

/** Full downtime issue detail + permission-gated lifecycle actions. */
export function IssueDetailScreen({ route, navigation }: Props) {
  const { id } = route.params;
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const getIssue = useDownTimeStore((s) => s.getIssue);
  const acknowledge = useDownTimeStore((s) => s.acknowledge);
  const resolve = useDownTimeStore((s) => s.resolve);
  const close = useDownTimeStore((s) => s.close);
  const remove = useDownTimeStore((s) => s.remove);
  const showToast = useToastStore((s) => s.show);
  const uaps = useResourcesStore((s) => s.uaps);
  const lines = useResourcesStore((s) => s.lines);
  const workstations = useResourcesStore((s) => s.workstations);
  const loadStructure = useResourcesStore((s) => s.loadStructure);

  const [issue, setIssue] = useState<DownTime | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadStructure();
    void getIssue(id).then((res) => {
      if (res.ok && res.data) setIssue(res.data);
      setLoading(false);
    });
  }, [id, getIssue, loadStructure]);

  const nameOf = useMemo(() => {
    const uMap = new Map(uaps.map((u) => [u.id, u.name]));
    const lMap = new Map(lines.map((l) => [l.id, l.name]));
    const wMap = new Map(workstations.map((w) => [w.id, w.name]));
    return { uap: uMap, line: lMap, station: wMap };
  }, [uaps, lines, workstations]);

  const runAction = async (
    action: (
      id: string,
    ) => Promise<{ ok: boolean; status: number; detail?: string }>,
  ) => {
    setBusy(true);
    const res = await action(id);
    setBusy(false);
    if (res.ok) {
      navigation.goBack();
    } else {
      showToast(res.status === 0 ? t("errors.network") : t("errors.generic"));
    }
  };

  const onDelete = () => {
    Alert.alert(
      t("downtime.detail.deleteTitle"),
      t("downtime.detail.deleteConfirm"),
      [
        { text: t("downtime.detail.cancel"), style: "cancel" },
        {
          text: t("downtime.detail.delete"),
          style: "destructive",
          onPress: () => void runAction(remove),
        },
      ],
    );
  };

  if (loading) {
    return (
      <View className="flex-1 items-center justify-center bg-slate-950">
        <ActivityIndicator color="#2dd4bf" />
      </View>
    );
  }

  if (!issue) {
    return (
      <View className="flex-1 items-center justify-center bg-slate-950 px-6">
        <Text className="text-sm text-slate-400">
          {t("downtime.detail.notFound")}
        </Text>
        <Pressable onPress={() => navigation.goBack()} className="mt-4">
          <Text className="text-teal-400">{t("downtime.detail.back")}</Text>
        </Pressable>
      </View>
    );
  }

  const meta = STATUS_META[issue.status];
  // Close-only tickets (material shortage / unknown cause) are never
  // acknowledged or resolved — the production agent just closes them. The
  // backend already returns can_acknowledge/can_resolve = false for them; this
  // guard keeps the screen correct against an older backend too.
  const closeOnly = isCloseOnly(issue.down_time_type);

  return (
    <ScrollView
      className="flex-1 bg-slate-950"
      contentContainerStyle={{
        paddingTop: insets.top + 8,
        paddingBottom: insets.bottom + 24,
        paddingHorizontal: 20,
      }}
    >
      <View className="flex-row items-center gap-3 py-3">
        <Pressable onPress={() => navigation.goBack()} hitSlop={12}>
          <Text className="text-2xl text-slate-300">‹</Text>
        </Pressable>
        <Text className="flex-1 text-xl font-bold text-white">
          {t(`downtime.type.${slug(issue.down_time_type)}`)}
        </Text>
        <View
          className="rounded-lg px-2.5 py-1"
          style={{ backgroundColor: meta.color + "22" }}
        >
          <Text className="text-xs font-medium" style={{ color: meta.color }}>
            {meta.emoji} {t(`downtime.status.${issue.status}`)}
          </Text>
        </View>
      </View>

      <Text className="mb-4 text-xs text-slate-400">
        {t(`downtime.process.${issue.process}`)} ·{" "}
        {t("downtime.list.inStatus", {
          time: formatDuration(issue.time_in_status_seconds),
        })}
      </Text>

      <View className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
        <Row
          label={t("downtime.detail.scope")}
          value={t(`downtime.scope.${slug(issue.down_time_scope)}`)}
        />
        {issue.uap_id && (
          <Row
            label={t("downtime.detail.uap")}
            value={nameOf.uap.get(issue.uap_id) ?? "—"}
          />
        )}
        {issue.production_line_id && (
          <Row
            label={t("downtime.detail.line")}
            value={nameOf.line.get(issue.production_line_id) ?? "—"}
          />
        )}
        {issue.workstation_id && (
          <Row
            label={t("downtime.detail.station")}
            value={nameOf.station.get(issue.workstation_id) ?? "—"}
          />
        )}
        <Row
          label={t("downtime.detail.createdAt")}
          value={humanTime(issue.created_at)}
        />
        <Row
          label={t("downtime.detail.createdBy")}
          value={issue.created_by_name ?? "—"}
        />
        {/* Keyed off the timestamps rather than the status: a close-only
            ticket is closed directly and never has them, while a legacy one
            created before its type became close-only may have been
            acknowledged before the rule changed — show what actually exists. */}
        {issue.acknowledged_at && (
          <>
            <Row
              label={t("downtime.detail.ackAt")}
              value={humanTime(issue.acknowledged_at)}
            />
            <Row
              label={t("downtime.detail.ackBy")}
              value={issue.acknowledged_by_name ?? "—"}
            />
          </>
        )}
        {issue.resolved_at && (
          <>
            <Row
              label={t("downtime.detail.resolvedAt")}
              value={humanTime(issue.resolved_at)}
            />
            <Row
              label={t("downtime.detail.resolvedBy")}
              value={issue.resolved_by_name ?? "—"}
            />
          </>
        )}
        {issue.status === "closed" && (
          <>
            <Row
              label={t("downtime.detail.closedAt")}
              value={humanTime(issue.closed_at)}
            />
            <Row
              label={t("downtime.detail.closedBy")}
              value={issue.closed_by_name ?? "—"}
              last
            />
          </>
        )}
      </View>

      <View className="mt-6 gap-3">
        {issue.can_acknowledge && !closeOnly && (
          <ActionButton
            label={t("downtime.detail.acknowledge")}
            onPress={() => void runAction(acknowledge)}
            busy={busy}
          />
        )}
        {issue.can_resolve && !closeOnly && (
          <ActionButton
            label={t("downtime.detail.resolve")}
            onPress={() => void runAction(resolve)}
            busy={busy}
          />
        )}
        {issue.can_close && (
          <ActionButton
            label={t("downtime.detail.close")}
            onPress={() => void runAction(close)}
            busy={busy}
          />
        )}
        {issue.can_delete && (
          <Pressable
            onPress={onDelete}
            disabled={busy}
            accessibilityRole="button"
            className="h-13 flex-row items-center justify-center rounded-2xl border border-red-500/50 py-3"
          >
            <Text className="text-base font-semibold text-red-400">
              {t("downtime.detail.delete")}
            </Text>
          </Pressable>
        )}
      </View>
    </ScrollView>
  );
}

function Row({
  label,
  value,
  last,
}: {
  label: string;
  value: string;
  last?: boolean;
}) {
  return (
    <View
      className={`flex-row justify-between py-2 ${last ? "" : "border-b border-slate-800"}`}
    >
      <Text className="text-sm text-slate-400">{label}</Text>
      <Text className="ml-4 flex-1 text-right text-sm text-white">{value}</Text>
    </View>
  );
}

function ActionButton({
  label,
  onPress,
  busy,
}: {
  label: string;
  onPress: () => void;
  busy: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={busy}
      accessibilityRole="button"
      className={`h-14 flex-row items-center justify-center rounded-2xl bg-teal-400 ${
        busy ? "opacity-60" : ""
      }`}
    >
      {busy ? (
        <ActivityIndicator color="#020617" />
      ) : (
        <Text className="text-base font-semibold text-slate-950">{label}</Text>
      )}
    </Pressable>
  );
}

export default IssueDetailScreen;
