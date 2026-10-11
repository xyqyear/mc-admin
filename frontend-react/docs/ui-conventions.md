# Frontend UI conventions

This page explains shared UI choices and composition. Protected source paths and
the allowed shadcn commands are defined in [frontend instructions](../AGENTS.md#generated-ui).

## Generated components

shadcn uses `base-nova` and `@base-ui/react`. Generated components import `cn`
from the `cn` package; `src/shared/lib/utils.ts` re-exports it for application
consumers. Keep project customizations in outer `shared/components/` or feature
UI so the official CLI can replace generated files without manual merges.

TypeScript uses JSX `preserve` with `noEmit`; Vite and Vitest apply the React
plugin's automatic runtime transform. This accepts upstream React namespace
imports while retaining strict and unused-code checks. Both TypeScript
configurations resolve the same `@/*` alias.

## Composition and feedback

- Base UI composition uses `render`/`useRender` or controlled state. Radix's
  `asChild` is not the component contract.
- `TooltipProvider` is mounted once in `src/main.tsx`.
- `Select` needs `itemToStringLabel` when its visible label differs from its
  value, such as `10` displayed as `10条/页`.
- Toasts come from Sonner. `useConfirm` accepts `title`, `description`,
  `confirmText`, `cancelText`, `variant` and `onConfirm`; rich content belongs in
  a state-driven `Dialog` because the confirmation helper has no `content` field.
- Declarative React Router APIs come from `react-router`. Ant Design components
  and icons are not part of the application stack.

Shared byte/duration formatting and filesystem-safe browser-local timestamps
live in `shared/utils/formatUtils.ts`. Callers choose their zero-value, precision,
unit-range and day/hour policies rather than silently changing the shared helper.

## Stateful controls

Keep workflow state with its controller and place reusable presentation under
the owning feature's public `ui/`. Preserve mounted owners when asynchronous
content disappears but a dialog or accepted operation must stay observable.
File batch controls have specific layout and eligibility rules in
[file operations](file-operations.md); map/history composition is described in
[the world restore page](world-restore-page.md).

Monaco worker setup and the YAML compatibility facade belong to
[editor integration](monaco-editor.md). Release-note editing and SemVer ordering
belong to [version updates](version-updates.md).
