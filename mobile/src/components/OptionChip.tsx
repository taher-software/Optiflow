import { Pressable, Text } from "react-native";

interface OptionChipProps {
  label: string;
  selected: boolean;
  onPress: () => void;
}

/** A single selectable chip used by OptionPicker. Presentational. */
export function OptionChip({ label, selected, onPress }: OptionChipProps) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      className={`rounded-xl border px-3 py-2 ${
        selected
          ? "border-teal-400 bg-teal-400/10"
          : "border-slate-700 bg-slate-900"
      }`}
    >
      <Text
        className={`text-sm font-medium ${
          selected ? "text-teal-200" : "text-slate-300"
        }`}
      >
        {label}
      </Text>
    </Pressable>
  );
}
