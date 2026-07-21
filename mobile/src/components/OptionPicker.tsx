import { Text, View } from "react-native";

import { OptionChip } from "./OptionChip";

export interface Option {
  value: string;
  label: string;
}

interface OptionPickerProps {
  label: string;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  /** Text shown when there are no options to choose from. */
  emptyText?: string;
}

/** Labeled single-select rendered as a wrap of selectable chips. */
export function OptionPicker({
  label,
  options,
  value,
  onChange,
  emptyText,
}: OptionPickerProps) {
  return (
    <View>
      <Text className="mb-2 text-sm font-medium text-slate-300">{label}</Text>
      {options.length === 0 && emptyText ? (
        <Text className="text-xs text-slate-500">{emptyText}</Text>
      ) : (
        <View className="flex-row flex-wrap gap-2">
          {options.map((o) => (
            <OptionChip
              key={o.value}
              label={o.label}
              selected={value === o.value}
              onPress={() => onChange(o.value)}
            />
          ))}
        </View>
      )}
    </View>
  );
}
