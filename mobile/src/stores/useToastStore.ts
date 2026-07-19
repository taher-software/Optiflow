import { create } from "zustand";

export type ToastKind = "error" | "success";

interface ToastState {
  message: string | null;
  kind: ToastKind;
  show: (message: string, kind?: ToastKind) => void;
  hide: () => void;
}

/** A tiny app-wide toast: one message at a time, rendered by <Toast />. */
export const useToastStore = create<ToastState>((set) => ({
  message: null,
  kind: "error",
  show: (message, kind = "error") => set({ message, kind }),
  hide: () => set({ message: null }),
}));
