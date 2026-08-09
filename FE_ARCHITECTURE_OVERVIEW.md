# Frontend architecture overview

`frontend/src/` layout and what belongs where:

- `main.tsx` — entrypoint, mounts `App` into `#root`.
- `App.tsx` — app root: wraps the router in the Redux `Provider`.
- `app/` — app shell, not feature code:
  - `router/` — `createBrowserRouter` route table (`index.tsx`).
  - `store/` — `configureStore` setup (`index.ts`), exports `RootState`/`AppDispatch`.
  - `redux/` — shared slices that don't belong to one feature module (e.g. auth/session state).
  - `guards/` — route guard components (e.g. `RequireAuth`) used in the router table.
  - `layouts/` — shared page shells (e.g. `DashboardLayout` with nav + outlet).
- `components/core/` — generic, reusable UI primitives with no feature knowledge (buttons, tables, modals).
- `pages/` — top-level route components (one per route), composed from `modules`/`components`.
- `modules/` — feature-specific code (e.g. a future `grading/` module: its own components, slice, hooks scoped to that feature) — keep feature logic here, not in `pages/`.
- `services/` — API clients (`api.ts` — fetch wrappers hitting the backend's `/api/v1/*`).
- `hooks/` — cross-feature custom hooks.
- `types/` — shared TypeScript types (mirrors backend Pydantic schemas, e.g. `grading.ts` mirrors `backend/app/schemas/grading.py`).
- `utils/` — pure helper functions with no React/Redux dependency.
- `styles/` — global CSS (`global.css`); feature-specific styles should live next to their component instead.

Path alias: `@/*` maps to `src/*` (configured in both `tsconfig.json` and `vite.config.ts`).
