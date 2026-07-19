import { useEffect } from "react";
import { Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useToastStore } from "../stores/useToastStore";

/** App-wide toast overlay. Renders the current message and auto-dismisses. */
export function Toast() {
  const message = useToastStore((s) => s.message);
  const kind = useToastStore((s) => s.kind);
  const hide = useToastStore((s) => s.hide);
  const insets = useSafeAreaInsets();

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(hide, 3500);
    return () => clearTimeout(timer);
  }, [message, hide]);

  if (!message) return null;

  return (
    <View
      className="absolute inset-x-0 items-center px-6"
      style={{ bottom: insets.bottom + 24 }}
      pointerEvents="none"
    >
      <View
        className={`w-full max-w-sm rounded-2xl px-4 py-3 ${
          kind === "error" ? "bg-red-500" : "bg-teal-500"
        }`}
        accessibilityRole="alert"
      >
        <Text className="text-center text-sm font-medium text-white">
          {message}
        </Text>
      </View>
    </View>
  );
}
