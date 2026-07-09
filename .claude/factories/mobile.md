# Mobile Sub-Factory

Builds the **React Native + TypeScript + TailwindCSS (NativeWind) + Zustand** app.

Everything follows one shared skill: **`.claude/skills/mobile/SKILL.md`** — the project
structure (screens / components / stores / routers / utils / constants), best practices + lint
gate, one Zustand store per component for backend data, and the data-population check.

In the Factory lane, mobile work is split into small Work Units. A data-bound unit
`depends_on` the backend BOM (its endpoint + response schema); it self-checks its inputs
before starting (**auto-control**) and its output — lint clean + data actually populates —
before hand-off (**firewall**).

> No specialized agent roster yet: the mobile sub-factory works from the shared skill.
> (Only the backend has specialized agents so far.)
