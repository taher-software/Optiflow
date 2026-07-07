---
name: mobile
description: >
  Use this skill for any OptiFlow mobile Work Unit (React Native + TypeScript +
  TailwindCSS via NativeWind + Zustand). Defines the mandatory project structure
  (screens / components / stores / routers / utils / constants), best-practice +
  linter requirements, the one-store-per-component pattern for backend data, and
  the data-population verification checklist every data-bound component must pass.
---

# Mobile Skill — OptiFlow Mobile Conventions (React Native · TS · Tailwind/NativeWind · Zustand)

This skill is consumed by every agent in the mobile sub-factory. It is the mobile twin of
the frontend skill: same discipline, React Native mechanics. It defines WHERE code lives,
the QUALITY bar (best practices + linting), HOW backend data is ingested (one Zustand store
per component when needed), and HOW to VERIFY a component fetches the right data and
populates as expected.

---

## 1. Project Structure (mandatory)

```
src/
  screens/      Route-level screens (the mobile "pages"). Compose components. Wiring only.
  components/   Small, single-purpose, presentational units. Each one VERY SIMPLE.
  stores/       Zustand stores. One per component/domain WHEN state is needed.
                Holds data fetched from the backend + loading/error state.
  routers/      Navigation config (React Navigation): stacks, tabs, route params.
  utils/        Pure, side-effect-free helpers. No RN, no fetching.
  constants/    App-wide constants, enums, config, route names.
```

- `screens/` is the mobile equivalent of the web `pages/`. Never put business logic or
  data fetching directly in a screen or component — it lives in a **store** (server data /
  shared state) or a **util** (pure logic).
- `{TO_FILL: confirm the actual src root and screens vs pages naming in this repo}`.

---

## 2. Best Practices (respect these — not optional)

- **TypeScript strict.** No `any`, no `@ts-ignore`. Every prop, store slice, navigation
  param, and API payload is explicitly typed (including typed React Navigation params).
- **Function components + hooks only.** No class components.
- **Components stay VERY SIMPLE.** One responsibility each; push logic into a store/util.
  Presentational components take typed props and render RN primitives (`View`, `Text`,
  `Pressable`, `FlatList`) — nothing more.
- **Styling via TailwindCSS/NativeWind `className`.** No inline `style={{}}` objects and no
  ad-hoc `StyleSheet.create` unless the project already uses it.
- **Container vs. presentational split:** a container reads a store + passes plain props to
  a simple presentational component.
- **Lists** use `FlatList`/`SectionList` with `keyExtractor` (never `.map()` over large
  data). **Accessibility:** `accessibilityLabel`, `accessibilityRole`, adequate hit targets.
- **No dead code, no `console.log` left in, no commented-out blocks.**

---

## 3. Linter Check (required before any unit is done)

Every Work Unit must pass, with **zero errors**, before its firewall lets it hand off:

```
eslint .            # @react-native / typescript-eslint rules
tsc --noEmit        # strict type check
prettier --check .  # formatting
```

Discover the exact scripts from `package.json` (e.g. `npm run lint`, `npm run typecheck`).
`{TO_FILL: pin the project's real lint/format/typecheck commands here.}`
If lint config is missing, raise an anomaly — do not silently skip the gate.

---

## 4. State & Backend Data — one Zustand store per component (when needed)

Presentational components with no server data need **no store**. A component that consumes
backend data gets a **dedicated Zustand store** (or a shared domain store) that owns the
ingestion:

```ts
// stores/useReportStore.ts
import { create } from "zustand";
import type { Report } from "../constants/types";   // mirrors backend ApiResponse shape

interface ReportState {
  data: Report | null;
  loading: boolean;
  error: string | null;
  fetchReport: (id: string) => Promise<void>;
}

export const useReportStore = create<ReportState>((set) => ({
  data: null,
  loading: false,
  error: null,
  fetchReport: async (id) => {
    set({ loading: true, error: null });
    try {
      const res = await api.get(`/reports/${id}`);   // endpoint from the BOM/API contract
      set({ data: res.data.data, loading: false });   // unwrap ApiResponse envelope
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },
}));
```

Rules:
- The store's data type **mirrors the backend contract exactly** (the `ApiResponse` payload
  produced by the backend sub-factory). Field names and types must match — this is the
  cross-factory contract, and it is the **same store shape as the web frontend** for the
  same resource.
- The store owns `data`, `loading`, `error` and the fetch action. Components never fetch
  directly.
- One store per component/domain **only if needed** — do not create empty stores.

---

## 5. Data-Population Verification (the mobile firewall check)

For **every data-bound component/screen**, verify — and state the evidence — that:

```
[ ] The store's typed shape matches the backend API contract (names + types)
[ ] The component triggers the CORRECT fetch (right endpoint / right store action)
[ ] The component subscribes to the CORRECT store selector (no stale/unrelated slice)
[ ] It handles all four states: loading, error, empty, and success
[ ] On success it renders the EXPECTED fields (the data actually populates the UI)
[ ] Lists use FlatList + keyExtractor and render the expected rows
[ ] No hardcoded/mock data left where a fetch should be
```

A unit is not done until its component demonstrably populates with the correct backend
data. If the backend contract it depends on is missing or mismatched, raise an anomaly and
reject back — never fake the data shape.

---

## 6. Quality Bar (before signaling a Work Unit done)

```
[ ] Code lands in the correct folder (screens/components/stores/routers/utils/constants)
[ ] Components are simple, typed, presentational; logic lives in stores/utils
[ ] TailwindCSS/NativeWind used for styling; no inline style objects
[ ] eslint + tsc --noEmit + prettier all pass with zero errors
[ ] Data-bound components pass the Section 5 verification
[ ] Navigation params are typed; routes registered in routers/
[ ] No console.log, no `any`, no dead/commented code
```

---

## 7. Anti-Patterns to Avoid

- Fetching inside a component/screen instead of a store
- Business logic inside a presentational component
- `any` / `@ts-ignore` to silence the type checker
- Inline `style={{}}` / stray `StyleSheet` instead of NativeWind classes
- A store whose shape drifts from the backend contract (or from the web store for the same resource)
- `.map()` over large lists instead of `FlatList`
- Components that render before handling loading/error/empty states
- Untyped navigation params
- Leaving mock data in place of a real fetch
