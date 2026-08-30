import { useTranslation } from "react-i18next";
import { Switch, Text, View } from "react-native";

interface OnlineToggleProps {
  /** Current reachability of the signed-in user. */
  online: boolean;
  /** True while the change is being sent — the switch is locked meanwhile. */
  pending: boolean;
  onChange: (online: boolean) => void;
}

/** Availability switch: lets a user declare themselves offline for team
 * notifications. Presentational — the state and the request live in the
 * auth store. */
export function OnlineToggle({ online, pending, onChange }: OnlineToggleProps) {
  const { t } = useTranslation();
  const stateLabel = online ? t("home.online.on") : t("home.online.off");

  return (
    <View className="mt-4 rounded-2xl border border-slate-800 bg-slate-900 px-4 py-3">
      <View className="flex-row items-center justify-between">
        <View className="flex-1 pr-3">
          <Text className="text-sm font-semibold text-white">
            {t("home.online.label")}
          </Text>
          <Text
            className={
              online
                ? "mt-1 text-xs font-semibold text-teal-400"
                : "mt-1 text-xs font-semibold text-slate-400"
            }
          >
            {stateLabel}
          </Text>
        </View>
        <Switch
          value={online}
          onValueChange={onChange}
          disabled={pending}
          accessibilityRole="switch"
          accessibilityLabel={t("home.online.label")}
          accessibilityState={{ checked: online, disabled: pending }}
          trackColor={{ false: "#334155", true: "#2dd4bf" }}
          thumbColor={online ? "#f8fafc" : "#94a3b8"}
          ios_backgroundColor="#334155"
        />
      </View>
      {!online && (
        <Text className="mt-2 text-xs leading-4 text-slate-400">
          {t("home.online.escalationNote")}
        </Text>
      )}
    </View>
  );
}

export default OnlineToggle;
