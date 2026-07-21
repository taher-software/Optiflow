import { useFocusEffect } from "@react-navigation/native";

/** Run `callback` every time the screen gains focus (e.g. to refetch after a
 * mutation on another screen). `callback` must be memoized by the caller. */
export function useFocusRefresh(callback: () => void): void {
  useFocusEffect(callback);
}
