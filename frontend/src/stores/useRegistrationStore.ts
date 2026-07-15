import { create } from "zustand";

import { API_URL } from "../constants/api";
import type { RegisterPayload } from "../constants/registration";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

async function post(path: string, body: unknown): Promise<ActionResult> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      return { ok: true };
    }
    let error = "Une erreur est survenue. Veuillez réessayer.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (data.detail) {
        error = data.detail;
      }
    } catch {
      // response had no JSON body — keep the default message
    }
    return { ok: false, error };
  } catch {
    return { ok: false, error: "Impossible de contacter le serveur." };
  }
}

interface RegistrationState {
  register: (payload: RegisterPayload) => Promise<ActionResult>;
  confirm: (token: string) => Promise<ActionResult>;
  resend: (email: string) => Promise<ActionResult>;
}

/**
 * Registration API actions (command-style POSTs). Components keep their own
 * local submitting/error state; these actions just return an ActionResult.
 */
export const useRegistrationStore = create<RegistrationState>(() => ({
  register: (payload) => post("/registration", payload),
  confirm: (token) => post("/registration/confirm", { token }),
  resend: (email) => post("/registration/resend", { email }),
}));
