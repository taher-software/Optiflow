import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { OptionPicker, type Option } from "../components/OptionPicker";
import {
  DOWN_TIME_TYPES,
  PRODUCTION_SCOPES,
  SETUP_CHANGEOVER,
  SETUP_DEPARTMENTS,
  slug,
  type CreateDownTimePayload,
  type DownTimeType,
  type ProductionScope,
} from "../constants/downtime";
import { type RootStackParamList } from "../constants/routes";
import { useDownTimeStore } from "../stores/useDownTimeStore";
import { useResourcesStore } from "../stores/useResourcesStore";
import { useToastStore } from "../stores/useToastStore";
import { conflictMessage } from "../utils/downTimeConflict";

type Props = NativeStackScreenProps<RootStackParamList, "DeclareDownTime">;

const INDEPENDENT = "__independent__";

/** Declare a new downtime — cascading scope → UAP → line → station, plus the
 * cause type and (for Setup / Changeover) the department. Production agents. */
export function DeclareDownTimeScreen({ navigation }: Props) {
  const { t, i18n } = useTranslation();
  const insets = useSafeAreaInsets();
  const uaps = useResourcesStore((s) => s.uaps);
  const lines = useResourcesStore((s) => s.lines);
  const workstations = useResourcesStore((s) => s.workstations);
  const loadStructure = useResourcesStore((s) => s.loadStructure);
  const createDownTime = useDownTimeStore((s) => s.createDownTime);
  const showToast = useToastStore((s) => s.show);

  const [scope, setScope] = useState<ProductionScope | "">("");
  const [uapSel, setUapSel] = useState("");
  const [lineSel, setLineSel] = useState("");
  const [stationSel, setStationSel] = useState("");
  const [type, setType] = useState<DownTimeType | "">("");
  const [department, setDepartment] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadStructure();
  }, [loadStructure]);

  // Only offer a scope when the plant actually has that structure.
  const scopeOptions: Option[] = useMemo(() => {
    return PRODUCTION_SCOPES.filter((s) => {
      if (s === "uap") return uaps.length > 0;
      if (s === "production line") return lines.length > 0;
      if (s === "work station") return workstations.length > 0;
      return true; // plant
    }).map((s) => ({ value: s, label: t(`downtime.scope.${slug(s)}`) }));
  }, [uaps, lines, workstations, t]);

  const showUap = scope !== "" && scope !== "plant";
  const showLine = scope === "production line" || scope === "work station";
  const showStation = scope === "work station";
  const showDepartment = type === SETUP_CHANGEOVER;

  const uapOptions: Option[] = useMemo(
    () => [
      ...uaps.map((u) => ({ value: u.id, label: u.name })),
      { value: INDEPENDENT, label: t("downtime.declare.independent") },
    ],
    [uaps, t],
  );

  const lineOptions: Option[] = useMemo(() => {
    const filtered =
      uapSel === INDEPENDENT
        ? lines.filter((l) => !l.uap_id)
        : uapSel
          ? lines.filter((l) => l.uap_id === uapSel)
          : [];
    const opts = filtered.map((l) => ({ value: l.id, label: l.name }));
    // A workstation can be independent of any line.
    if (scope === "work station") {
      opts.push({
        value: INDEPENDENT,
        label: t("downtime.declare.independent"),
      });
    }
    return opts;
  }, [lines, uapSel, scope, t]);

  const stationOptions: Option[] = useMemo(() => {
    const filtered =
      lineSel === INDEPENDENT
        ? workstations.filter((w) => !w.production_line_id)
        : lineSel
          ? workstations.filter((w) => w.production_line_id === lineSel)
          : [];
    return filtered.map((w) => ({ value: w.id, label: w.name }));
  }, [workstations, lineSel]);

  const typeOptions: Option[] = DOWN_TIME_TYPES.map((ty) => ({
    value: ty,
    label: t(`downtime.type.${slug(ty)}`),
  }));

  const departmentOptions: Option[] = SETUP_DEPARTMENTS.map((d) => ({
    value: d,
    label: t(`downtime.process.${d}`),
  }));

  // Reset dependents when a parent selection changes.
  const onScope = (v: string) => {
    setScope(v as ProductionScope);
    setUapSel("");
    setLineSel("");
    setStationSel("");
  };
  const onUap = (v: string) => {
    setUapSel(v);
    setLineSel("");
    setStationSel("");
  };
  const onLine = (v: string) => {
    setLineSel(v);
    setStationSel("");
  };
  const onStation = (v: string) => {
    setStationSel(v);
  };
  const onType = (v: string) => {
    setType(v as DownTimeType);
    setDepartment("");
  };

  const valid =
    scope !== "" &&
    type !== "" &&
    (scope !== "uap" || (uapSel !== "" && uapSel !== INDEPENDENT)) &&
    (scope !== "production line" ||
      (lineSel !== "" && lineSel !== INDEPENDENT)) &&
    (scope !== "work station" || stationSel !== "") &&
    (type !== SETUP_CHANGEOVER || department !== "");

  const submit = async () => {
    if (!valid) return;
    const payload: CreateDownTimePayload = {
      production_scope: scope,
      uap_id:
        scope === "plant" || uapSel === "" || uapSel === INDEPENDENT
          ? null
          : uapSel,
      production_line_id:
        showLine && lineSel !== "" && lineSel !== INDEPENDENT ? lineSel : null,
      workstation_id: showStation && stationSel !== "" ? stationSel : null,
      down_time_type: type,
      department:
        type === SETUP_CHANGEOVER
          ? (department as "production" | "maintenance")
          : null,
    };
    setBusy(true);
    const res = await createDownTime(payload);
    setBusy(false);
    if (res.ok) {
      showToast(t("downtime.declare.success"), "success");
      navigation.goBack();
      return;
    }
    // 409: the target, or one of its ancestors, is already down. The backend
    // sends the explanation in both languages; show the app's own language.
    if (res.status === 409) {
      showToast(
        conflictMessage(res.detailBody, i18n.language) ??
          t("downtime.declare.conflict"),
      );
      return;
    }
    showToast(res.status === 0 ? t("errors.network") : t("errors.generic"));
  };

  return (
    <ScrollView
      className="flex-1 bg-slate-950"
      contentContainerStyle={{
        paddingTop: insets.top + 8,
        paddingBottom: insets.bottom + 32,
        paddingHorizontal: 20,
      }}
    >
      <View className="flex-row items-center gap-3 py-3">
        <Pressable onPress={() => navigation.goBack()} hitSlop={12}>
          <Text className="text-2xl text-slate-300">‹</Text>
        </Pressable>
        <Text className="text-xl font-bold text-white">
          {t("downtime.declare.title")}
        </Text>
      </View>

      <View className="mt-2 gap-6">
        <OptionPicker
          label={t("downtime.declare.scope")}
          options={scopeOptions}
          value={scope}
          onChange={onScope}
        />

        {showUap && (
          <OptionPicker
            label={t("downtime.declare.uap")}
            options={uapOptions}
            value={uapSel}
            onChange={onUap}
          />
        )}

        {showLine && (
          <OptionPicker
            label={t("downtime.declare.line")}
            options={lineOptions}
            value={lineSel}
            onChange={onLine}
            emptyText={t("downtime.declare.noLines")}
          />
        )}

        {showStation && (
          <OptionPicker
            label={t("downtime.declare.station")}
            options={stationOptions}
            value={stationSel}
            onChange={onStation}
            emptyText={t("downtime.declare.noStations")}
          />
        )}

        <OptionPicker
          label={t("downtime.declare.type")}
          options={typeOptions}
          value={type}
          onChange={onType}
        />

        {showDepartment && (
          <OptionPicker
            label={t("downtime.declare.department")}
            options={departmentOptions}
            value={department}
            onChange={setDepartment}
          />
        )}

        <Pressable
          onPress={submit}
          disabled={!valid || busy}
          accessibilityRole="button"
          className={`h-14 flex-row items-center justify-center rounded-2xl bg-teal-400 ${
            !valid || busy ? "opacity-60" : ""
          }`}
        >
          {busy ? (
            <ActivityIndicator color="#020617" />
          ) : (
            <Text className="text-base font-semibold text-slate-950">
              {t("downtime.declare.save")}
            </Text>
          )}
        </Pressable>
      </View>
    </ScrollView>
  );
}

export default DeclareDownTimeScreen;
