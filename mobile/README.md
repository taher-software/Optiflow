# OptiFlow — Mobile

**Stack:** React Native · TypeScript · TailwindCSS (NativeWind) · Zustand.

## Structure

```
src/
  screens/      Route-level screens (mobile "pages"); compose components; wiring only
  components/    Small, simple, presentational RN units
  stores/        Zustand stores — one per component/domain when needed; holds backend data
  routers/       Navigation config (React Navigation): stacks, tabs, typed params
  utils/         Pure helpers (no RN, no fetching)
  constants/     App-wide constants, enums, route names
```

Each component stays **very simple**; data fetching + logic live in a store/util. Store
shapes mirror the backend `ApiResponse` contract — the **same shape** the web store uses
for the same resource.

## Governed by

- Sub-factory: `.claude/factories/mobile.md`
- Skill: `.claude/skills/mobile/SKILL.md`
