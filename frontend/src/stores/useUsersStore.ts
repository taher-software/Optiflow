import { create } from "zustand";

import { API_URL } from "../constants/api";
import type {
  CreateUserPayload,
  UpdateUserPayload,
  User,
} from "../constants/users";
import { authHeader } from "./useAuthStore";

export interface Result<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

async function request<T>(
  path: string,
  method: string,
  body?: unknown,
): Promise<Result<T>> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.ok) {
      const json = (await res.json()) as { data: T };
      return { ok: true, data: json.data };
    }
    let error = "Une erreur est survenue. Veuillez réessayer.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (data.detail) error = data.detail;
    } catch {
      // no JSON body
    }
    return { ok: false, error };
  } catch {
    return { ok: false, error: "Impossible de contacter le serveur." };
  }
}

interface UsersState {
  users: User[];
  loading: boolean;
  error: string | null;
  fetchUsers: () => Promise<void>;
  createUser: (payload: CreateUserPayload) => Promise<Result<User>>;
  getUser: (id: string) => Promise<Result<User>>;
  updateUser: (id: string, payload: UpdateUserPayload) => Promise<Result<User>>;
}

/** User-management state. The list (data/loading/error) is owned here;
 * create/get/update are command actions returning a Result. */
export const useUsersStore = create<UsersState>((set) => ({
  users: [],
  loading: false,
  error: null,

  fetchUsers: async () => {
    set({ loading: true, error: null });
    const res = await request<User[]>("/users", "GET");
    if (res.ok) set({ users: res.data ?? [], loading: false });
    else set({ error: res.error ?? "Erreur", loading: false });
  },

  createUser: (payload) => request<User>("/users", "POST", payload),
  getUser: (id) => request<User>(`/users/${id}`, "GET"),
  updateUser: (id, payload) => request<User>(`/users/${id}`, "PUT", payload),
}));
