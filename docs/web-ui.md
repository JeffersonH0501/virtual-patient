# Web UI

The UI uses React, Vite, TypeScript and Tailwind. [index.css](../virtual-patient-ui/src/index.css) loads Tailwind and the [design system](../virtual-patient-ui/src/styles/design-system.css). Keep state, accessible markup and measured values in components. Define shared appearance in the design system.

## Layout and tokens

Use `--content-max-width` for page width. Authentication panel widths derive from the same token. The page shell owns the outer inset. Prefer the existing layout spacing tokens (15 px inset, 10 px component gap, 5 px compact gap). Add responsive rules for a change in arrangement. Preserve measured media geometry, calibration targets and viewport-constrained dialog bodies.

Reuse shared Inter typography, semantic color tokens and Lucide icons. Use sentence case in the Spanish and English translations. Preserve clinical content, names and values received from the API. Give icon-only actions an accessible name and preserve visible keyboard focus.

## Shared components

| Task | Component or convention |
| --- | --- |
| Actions and navigation | `Button`, `ui-button-group` and `ui-icon-button`. Use semantic variants and native disabled controls. |
| Status and categories | `Badge`. Use the semantic tone for the actual state. |
| Forms | `Field` for labels, errors and hints. `Select` for the shared keyboard-operable selector. Preserve native form semantics and invalid-field focus. |
| Pages and lists | `PageHeader`, `ListPanel`, native tables and `ui-table-scroll`. Give headings and table actions accessible names. Commit new rows and pagination together after a successful read. |
| Dialogs | `Dialog` and shared action groups. Keep headers and actions visible and scroll the body. Restore focus on close. Keep unsaved input after a recoverable error. |
| Scores | `EvaluationScore` and the shared [score utilities](../virtual-patient-ui/src/utils/evaluationScore.ts). Preserve the 0–5 scale and one-decimal display. |

## Review and motion

Review uses the API's capabilities for evaluation sources, assignment actions and technical detail. The replay uses the private preview and points the transcript to the corresponding position. Keep an available transcript usable when media or scoring is pending. Keep editable ratings private and preserve unsaved edits through recoverable failures.

The root [App](../virtual-patient-ui/src/App.tsx) runs one `MotionProvider` and one `useInputViewport`. Use the shared motion primitives for entries, disclosures and dialogs. Respect reduced motion. Keep decorative transforms away from camera, video and calibration coordinates. Mobile text entry should preserve native zoom and let the shared viewport hook scroll an occluded field into view.

## Validation

Run affected component tests in Docker. For changes to shared styling or layout, check representative desktop and mobile views with keyboard and reduced motion. Validate capture and playback with physical devices when affected.

```bash
docker compose -f docker-compose.local.yml exec ui yarn lint
docker compose -f docker-compose.local.yml exec ui yarn build
```
