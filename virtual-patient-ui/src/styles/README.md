# UI design system

`design-system.css` is the single application stylesheet and source of truth for
visual decisions. `src/index.css` only imports Tailwind and this file; both the
application and the icon gallery load that entry point. Components select
semantic classes and variants rather than defining CSS values in JavaScript.

## Where to change a value

| Area | Tokens or selectors in design-system.css |
| --- | --- |
| Dialog widths | `--dialog-width-small`, `--dialog-width-medium`, `--dialog-width-large` |
| Dialog viewport limits | `--dialog-viewport-inline-gap`, `--dialog-viewport-block-gap`, `--dialog-content-max-height` |
| Overlay and stacking | `--dialog-overlay-opacity`, `--z-modal`, `--z-tooltip` |
| Content and tables | `--layout-content-width`, `--layout-table-width`, `table-column-*` utilities |
| Interview columns | `--call-stage-height-width`, `grid-cols-simulation-*`, `grid-cols-results-desktop` |
| Authentication | `--auth-*`, `.auth-*` and their responsive rules |
| Buttons, badges, scores | `.ui-button*`, `.ui-badge*`, `.evaluation-score*` |
| Motion and portal removal | `--motion-*` and the named keyframes; keep removal delay at least as long as exit animation |
| Audio visualization | `--wave-*`, `.voice-wave`, `.patient-voice-wave` |
| Interview calibration | `.calibration-*` components and `--calibration-level` |
| Recorded canvas appearance | `--recording-*` |

`<Modal size="large">` still selects the large variant, but its width now comes
from CSS. There is no `MODAL_SIZES` object to edit. Responsive utilities such as
`md:grid-cols-simulation-tablet` are generated from central `@utility` rules.

## What stays in components

Keep structural Tailwind utilities such as `flex`, `grid`, `gap-2` and responsive
visibility at the call site; their values already derive from the central theme.
Keep text, validation, score thresholds, recording resolution/frame rate,
coordinates tied to media data, and session timing in TypeScript.

Only dynamic data uses inline custom properties: `--wave-level`,
`--progress-width`, and an explicitly requested `--modal-overlay-opacity`.
Their visual interpretation lives in CSS. JavaScript timers and Canvas APIs use
`utils/designTokens.ts` to read CSS values because those APIs cannot directly
consume CSS variables. Canvas appearance is captured once when recording starts.
SVG paths, viewBox coordinates and illustration assets remain source artwork.

Do not add component CSS files, injected `<style>` blocks, literal visual sizes,
or color values in TSX. Add a named utility or component variant here instead.


## Typography

- Use the shared `font-sans` family.
- Use the defined Tailwind scale: `text-xs`, `text-sm`, `text-base`, `text-lg`, `text-xl`, `text-2xl`, `text-3xl`, and `text-4xl`.
- Prefer `font-medium` for controls, `font-semibold` for section titles, and `font-bold` only for primary page-level emphasis.
- Do not introduce inline `fontFamily` or arbitrary font sizes without a documented product requirement.
- Use `component-title` for the title of reusable panels and cards. It standardizes these headings as `text-sm`, `font-semibold`, and `slate-800`.
- Use `component-subtitle` for headings nested inside those panels and cards. It keeps the same size and weight while using `slate-700`.
- Use `dialog-actions` around dialog action buttons and `dialog-action` with its semantic variant. The grid gives every action the width required by the longest label in the group.
- Dialogs use a single top header strip and one surface color throughout. Dialogs with footer actions must set `hasActions`, omit the close icon, and can only close through those actions. Informational dialogs use a close icon and allow outside-click dismissal.
- Dialog widths use only three sizes: `small` (448 px), `medium` (640 px), and `large` (880 px), always constrained by the viewport.
- Use `dialog-info-callout` for exceptional informational notes that need a contained blue treatment inside an otherwise linear dialog.
- Use `dialog-copy` for dialog descriptions and body text so typography follows the Information dialog consistently.
- Use `dialog-close-button` for the close control of informational dialogs; it provides the shared soft neutral surface and blue hover state.

## Colors

New components should prefer semantic tokens:

- Brand and interactive states: `brand-*`
- Text and neutral surfaces: `neutral-*`, `content`, and `content-muted`
- Success: `success-*`
- Errors and destructive actions: `danger-*`
- Warnings and ratings: `warning-*`
- Surfaces and borders: `surface`, `surface-subtle`, and `border`

Slate is the default text hierarchy across the application: body copy and descriptions use `slate-600`, subtitles use `slate-700`, and titles use `slate-800`. Semantic states such as brand actions, success, danger, and warning keep their corresponding palettes.

The shared Tailwind spacing unit is `0.225rem`. Spacing-based utilities derive their dimensions from that global unit.

Keyboard focus uses one global three-pixel `warning-400` outline without an offset. Component-level Tailwind rings are neutralized so controls do not display competing focus treatments. Use `data-focus-outline="none"` only when an equivalent accessible focus indicator is provided by the component.

Legacy `blue`, `gray`, `slate`, `green`, `emerald`, `red`, `rose`, `yellow`, and `amber` utilities are mapped to the same centralized palettes. This keeps existing screens consistent while new work adopts semantic names.

Avoid literal hex, RGB, or arbitrary Tailwind color values in components. Canvas rendering reads `--recording-*` through the design-token adapter. Values received dynamically from data remain in code.

Evaluation scores use a global 0-5 scale. `src/utils/evaluationScore.ts` owns the limits, formatting, and bands: 0-2.9 is `danger`, 3-3.9 is `warning`, and 4-5 is `success`. Evaluation views must use those helpers instead of defining local thresholds.
Render numeric ratings with the shared `EvaluationScore` component. It always shows one decimal, keeps the colored score and muted `/ 5` scale consistent, and allows only the visual size to vary.

## Shape and elevation

Use the shared `control`, `card`, and `panel` radii and the `card`, `card-hover`, and `modal` shadows instead of introducing new arbitrary values.

## Changing the visual system

Change tokens in `design-system.css`, then run:

```bash
corepack yarn build
```

This updates current Tailwind utilities and semantic utilities from one place.

Dialogs share typography through `.modal-panel` in `design-system.css`: `.dialog-title` marks the main heading; other headings are subtitles; paragraphs and native ordered/unordered lists share the body scale. `.dialog-annotation` provides a smaller blue callout with the only decorative content border. Inputs retain their functional borders. `extralarge` uses `--dialog-width-extralarge` (1200px), still constrained to the viewport, and is used by turn details.

Dialog headers retain a bottom divider. `--dialog-content-gap` defines the 16px gap before action rows; the preceding body has no bottom padding to avoid doubling that space. All annotation descendants and list markers inherit the blue annotation color.
