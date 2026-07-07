---
name: frontend
description: >
  Use this skill for any OptiFlow web frontend Work Unit (React + TypeScript +
  TailwindCSS + Zustand). Defines the mandatory project structure
  (pages / components / stores / routers / utils / constants), best-practice +
  linter requirements, the one-store-per-component pattern for backend data, and
  the data-population verification checklist every data-bound component must pass.
---

# Frontend Skill — OptiFlow Web Conventions (React · TS · Tailwind · Zustand)

This skill is consumed by every agent in the frontend sub-factory. It defines WHERE
code lives, the QUALITY bar (best practices + linting), HOW backend data is ingested
(one Zustand store per component when needed), and HOW to VERIFY a component fetches
the right data and populates as expected.

---

## 1. Project Structure (mandatory)

```
src/
  pages/        Route-level screens. Compose components. Minimal logic — wiring only.
  components/   Small, single-purpose, presentational units. Each one VERY SIMPLE.
  stores/       Zustand stores. One per component/domain WHEN state is needed.
                Holds data fetched from the backend + loading/error state.
  routers/      Route definitions / navigation config (react-router).
  utils/        Pure, side-effect-free helpers. No React, no fetching.
  constants/    App-wide constants, enums, config, route paths.
```

- Never put business logic or data fetching directly in a component or page — it lives
  in a **store** (server data / shared state) or a **util** (pure logic).
- `{TO_FILL: confirm the actual src root and whether "routers" is singular/plural in this repo}`.

---

## 2. Best Practices (respect these — not optional)

- **TypeScript strict.** No `any`, no `@ts-ignore`. Every prop, store slice, and API
  payload is explicitly typed.
- **Function components + hooks only.** No class components.
- **Components stay VERY SIMPLE.** One responsibility each; if a component grows branching
  logic or fetches, split it or push logic into a store/util. Presentational components
  take typed props and render — nothing more.
- **Styling via TailwindCSS utility classes.** No inline `style={{}}` objects, no ad-hoc
  CSS files unless the project already uses them.
- **Container vs. presentational split:** a container reads a store + passes plain props to
  a simple presentational component.
- **Accessibility:** semantic elements, `alt`, labels, keyboard focus where relevant.
- **No dead code, no `console.log` left in, no commented-out blocks.**

---

## 3. Linter Check (required before any unit is done)

Every Work Unit must pass, with **zero errors**, before its firewall lets it hand off:

```
eslint .            # typescript-eslint rules
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
  cross-factory contract.
- The store owns `data`, `loading`, `error` and the fetch action. Components never fetch
  directly.
- One store per component/domain **only if needed** — do not create empty stores.

---

## 5. Data-Population Verification (the frontend firewall check)

For **every data-bound component**, verify — and state the evidence — that:

```
[ ] The store's typed shape matches the backend API contract (names + types)
[ ] The component triggers the CORRECT fetch (right endpoint / right store action)
[ ] The component subscribes to the CORRECT store selector (no stale/unrelated slice)
[ ] It handles all four states: loading, error, empty, and success
[ ] On success it renders the EXPECTED fields (the data actually populates the UI)
[ ] No hardcoded/mock data left where a fetch should be
```

A unit is not done until its component demonstrably populates with the correct backend
data. If the backend contract it depends on is missing or mismatched, raise an anomaly and
reject back — never fake the data shape.

---

## 6. Quality Bar (before signaling a Work Unit done)

```
[ ] Code lands in the correct folder (pages/components/stores/routers/utils/constants)
[ ] Components are simple, typed, presentational; logic lives in stores/utils
[ ] TailwindCSS used for styling; no inline style objects
[ ] eslint + tsc --noEmit + prettier all pass with zero errors
[ ] Data-bound components pass the Section 5 verification
[ ] No console.log, no `any`, no dead/commented code
```

---

## 7. Anti-Patterns to Avoid

- Fetching inside a component/page instead of a store
- Business logic inside a presentational component
- `any` / `@ts-ignore` to silence the type checker
- Inline style objects instead of Tailwind classes
- A store whose shape drifts from the backend contract
- Components that render before handling loading/error/empty states
- Giant "god" components — split them; keep each one very simple
- Leaving mock data in place of a real fetch
