# OptiFlow — Frontend (Web)

**Stack:** React · TypeScript · TailwindCSS · Zustand.

## Structure

```
src/
  pages/        Route-level screens; compose components; wiring only
  components/    Small, simple, presentational units
  stores/        Zustand stores — one per component/domain when needed; holds backend data
  routers/       Route definitions / navigation (react-router)
  utils/         Pure helpers (no React, no fetching)
  constants/     App-wide constants, enums, route paths
```

Each component stays **very simple**; data fetching + logic live in a store/util, not the
component. Store shapes mirror the backend `ApiResponse` contract exactly.

## Governed by

- Sub-factory: `.claude/factories/frontend.md`
- Skill: `.claude/skills/frontend/SKILL.md`
