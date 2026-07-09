# Frontend Sub-Factory

Builds the **React + TypeScript + TailwindCSS + Zustand** web app.

Everything follows one shared skill: **`.claude/skills/frontend/SKILL.md`** — the project
structure (pages / components / stores / routers / utils / constants), best practices + lint
gate, one Zustand store per component for backend data, and the data-population check.

In the Factory lane, frontend work is split into small Work Units. A data-bound unit
`depends_on` the backend BOM (its endpoint + response schema); it self-checks its inputs
before starting (**auto-control**) and its output — lint clean + data actually populates —
before hand-off (**firewall**).

> No specialized agent roster yet: the frontend sub-factory works from the shared skill.
> (Only the backend has specialized agents so far.)
