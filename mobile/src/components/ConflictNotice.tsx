import { Pressable, Text, View } from "react-native";

interface ConflictNoticeProps {
  title: string;
  message: string;
  /** Secondary lines: the blocking ticket reference, the parent-level note. */
  details?: readonly string[];
  /** Label of the "open the existing ticket" action, when one is available. */
  actionLabel?: string;
  onAction?: () => void;
}

/** Inline banner telling the user the target (or a parent of it) is already
 * down, and that the existing ticket should be updated instead. */
export function ConflictNotice({
  title,
  message,
  details = [],
  actionLabel,
  onAction,
}: ConflictNoticeProps) {
  return (
    <View
      className="gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/10 px-4 py-3"
      accessibilityRole="alert"
    >
      <Text className="text-base font-semibold text-amber-200">{title}</Text>
      <Text className="text-sm text-amber-100">{message}</Text>
      {details.map((line) => (
        <Text key={line} className="text-xs text-amber-200/80">
          {line}
        </Text>
      ))}
      {actionLabel && onAction ? (
        <Pressable
          onPress={onAction}
          accessibilityRole="button"
          hitSlop={8}
          className="mt-1 self-start rounded-xl bg-amber-400 px-4 py-2"
        >
          <Text className="text-sm font-semibold text-slate-950">
            {actionLabel}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export default ConflictNotice;
