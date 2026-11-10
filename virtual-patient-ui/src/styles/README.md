# UI design system

`design-system.css` is the single application stylesheet. `src/index.css` imports Tailwind and this file only. Keep component appearance here; React provides state, accessible markup and dynamic measurements.

## File structure and cascade

1. Design tokens: semantic colors, typography, spacing, geometry, radii, elevation and motion.
2. Base: document defaults and keyboard focus, in `@layer base`.
3. Shared components: each component's base, meaningful variants, interaction states and responsive rules, in `@layer components`.
4. Specialized layouts: authentication, media/session, calibration and review, in `@layer components`.
5. Named functional utilities and animations.

Utilities may customize layout, but consumers must not redefine a shared component's colors, padding, typography or states. Use explicit classes rather than selectors that guess appearance from SVGs, sibling elements or child combinations. Remove unused rules instead of appending corrective overrides. Native checkbox state selectors in assignment rows remain functional state styling.

## Spacing and geometry

| Purpose | Tokens | Value |
| --- | --- | --- |
| Page boundary and panel/dialog/menu interior | `--layout-inset` | 15px |
| Space between components | `--layout-gap` | 10px |
| Compact spacing between interview-summary rows and small actions | `--layout-gap-small` | 5px |
| Small boxed buttons | `--button-small-padding-block/inline` | 5px 10px |
| Large tabs and final form/dialog actions | `--button-large-padding-block/inline` | 10px 15px |
| Small icon-only buttons and pagination arrows | `--icon-button-small-padding` | 5px on every side |
| Large icon-only buttons, including Info/Profile and dialog close controls | `--icon-button-large-padding` | 10px on every side |
| Small and text-action internal gap | `--button-small-gap` | 5px |
| Large-action internal gap | `--button-large-gap` | 10px |
| Badge padding | `--badge-padding-block/inline` | 5px 10px |

`ui-viewport` owns the outer inset once. `ui-page` centers normal pages at `--content-max-width: 1000px`; wide screens can have larger side gutters. Authentication uses the same minimum boundary. Responsive layouts change arrangement, not spacing values.

Top-bar height follows the navigation button line box plus its padding through --header-control-height. The logo and icon-only Info/Profile actions fit that height; they cannot make the bar taller. Desktop columns share the same bottom edge and 15px inset above the header divider. Mobile navigation can wrap into an extra row using one parent-owned gap without an extra divider/inset. Panel headers center titles and actions vertically and contain no descriptive captions.

Use `gap-layout`, `space-y-layout` and `p*-inset` for shared layout. Let one parent own each gap or inset. Joined surfaces can intentionally have zero gaps. Buttons, fields, assignment rows and loading/empty states use content and padding rather than positive minimum dimensions. Inputs, selects and read-only values share 10px padding and a 20px line box; textarea rows retain their explicit multiline purpose. Do not impose minimum widths on tables, evaluation selectors or call timers.

Keep `min-width: 0` and `min-height: 0` where flex/grid children must shrink for scrolling or wrapping. The authenticated application shell uses the shared visible viewport height (`--app-viewport-height`, falling back to `100dvh`), with a non-shrinking navigation header outside the scrollable `main`. Lists scroll inside `main`; their footer remains at the end of that same scroll area and stays at the viewport bottom when content is short. Route changes reset the main scroll position. Review keeps its existing panel layout, with main scrolling below the header on small screens. Calibration and active sessions retain their dedicated internal scrolling. Only the application shell and authentication page fill the viewport vertically; do not repeat that minimum on body/root or individual panels. Media aspect ratios, calibration geometry and viewport limits on scrollable dialogs remain functional constraints. Consolidate repeated responsive rules instead of redeclaring unchanged spacing.

Do not change Tailwind's numeric `--spacing`: it also controls icon sizes and functional geometry. Preserve shared select arrow spacing, focus outlines, media waveform geometry and viewport-based calibration targets.

## Shared components

### Buttons and navigation

Use `Button` for ordinary actions. Its variants are `primary`, `secondary`, `text` and `danger`. Secondary actions may use `ui-button--hover-danger` or `ui-button--hover-warning` for a soft red/yellow hover while retaining the gray resting surface. Disabled controls retain their existing neutral state. Standard boxed actions and all pagination controls use the small padding. Navigation tabs and final dialog/form/calibration actions use large padding. Apply ui-button-group--large to explicit final-action groups; dialog-actions and dialog-footer already select large boxed actions. Previous/next pagination uses secondary icon-only buttons with Lucide chevrons, aria-label and title. Pagination widths follow content and padding; do not impose equal tracks or fixed widths.

Text actions use `variant="text"` or `ui-action-text`: transparent surface and zero padding. Text plus an icon uses the same explicit text-action pattern. Icon-only controls use `ui-icon-button` with the shared boxed-button colors and 5px padding on every side; add `ui-icon-button--large` for 10px padding on every side. Dialog close controls use large icon padding; pagination arrows use small icon padding. Final-action groups do not override explicit icon-only sizing. Meaningful modifiers are `--brand`, `--danger`, `--warning` and `--inverse` for dark media controls. Supply an accessible button name. Info and Profile use large boxed `header-action` controls without visible text, with 10px padding on every side and accessible names/tooltips. Their icon dimensions and button height follow the navigation tabs. Case-library disclosure arrows use the explicit transparent `case-disclosure` exception.

Adding an icon does not change a button's appearance automatically. Select the intended action pattern explicitly. Icon and label inherit the same color.

Small and text-action groups use ui-button-group with a 5px gap; table text options also use 5px. Final dialog actions and ui-button-group--large use 10px. The top-bar Info/Profile group uses 10px between its icon-only actions. Navigation tabs use ui-navigation with 10px. Component-to-component spacing outside action groups remains 10px.

Primary/danger actions preserve their background while disabled and use `--button-disabled-filled-content` (translucent white). Secondary, text and icon actions use `--button-disabled-content`. Disabled controls retain full opacity, do not react to hover, and require native disabled semantics or handler guards. All keyboard-operable controls retain visible focus.

### Badges

Import `Badge` from `components/common/Badge`. Use it for statuses, roles, clinical tags, categories and compact informational labels. Every badge has 5px vertical/10px horizontal padding, 12px text, weight 500, a 20px line box and a pill radius. Layout classes and native span attributes are supported; do not override appearance at call sites.

| Tone | Meaning |
| --- | --- |
| `neutral` | Descriptive/category label without a status implication |
| `info` | Informational role, relationship or in-progress status |
| `success` | Completed or positive status |
| `warning` | Caution or an improvement opportunity |
| `danger` | Interrupted, active problem or negative status |

Map API values to visual tones without changing clinical data. Avatars, recording dots, loaders, progress graphics and `EvaluationScore` values are not badges. Never infer a clinical state from a color.

The case-availability count uses `info` (blue); the account-role badge in the profile menu uses `success` (green). Role labels and authorization remain unchanged.

The profile menu sign-out action uses the shared danger button with large action padding.

### Fields, panels and tables

`Field` owns standard input labels, password visibility, hints and errors. `AuthField` remains its compatibility export. All visible selectors use `common/Select`: the evaluation source, case configuration, case forms and user roles share its trigger, Lucide chevron, blue focus, popup, selected/active options and disabled states. `CustomSelect` wraps string options and labels; `FormInput` retains existing textarea/select/input consumers. Do not add route-specific dropdown implementations or native visible selectors.

`Select` accepts controlled string values, `SelectOption` labels (including rich text), disabled options, placeholder, name, required and ARIA attributes. Use `onValueChange` for string callbacks; legacy field `onChange` receives an actual native select change event. A non-interactive hidden select preserves FormData, required validation and disabled-field omission. Invalid submission focuses the visible control and exposes a localized error. Forwarded refs focus the visible button. Menus use a body portal or the dialog scroll host, maintain their owner's outside-click boundary, and consume the first Escape without dismissing a dialog. The shared menu maximum is `--select-menu-max-height`; all colors, paddings and typography remain central tokens.

Use `ui-panel`, `ui-panel-header`, `ui-panel-body` and `ui-panel-section`. Cases, interviews and users reuse `PageHeader` for their shared eyebrow, page title, divider and responsive spacing; its optional children hold existing trailing content such as the case-count badge. Page titles are h1. Listing pages use `ListPanel`, which owns its h2 title, actions and pagination. Panel headers show only their title and applicable actions, without descriptive subtitles. Native table captions remain visually hidden for accessibility. The clinical-case library remains unpaginated.

Tables remain native tables within `ui-table-scroll`. Cells use 10px padding and vertical centering. Column headings use sentence case from translations; body data keeps its original casing. Text actions stack through `ui-table-options`. Interview View/Delete actions use `ui-table-options--icons` in one row, with small `ui-icon-button` controls and Lucide Eye/Trash2 icons: View is secondary and Delete is secondary with a soft danger hover; keep accessible labels, tooltips and existing disabled states. Assigned reviews keep only their authorized View action. `Pagination` keeps server totals or visited-page behavior and the shared ten-row page size. The case-availability count uses Badge. The application footer is one paragraph with line breaks and no margins between its lines.

Use `ui-notice` for success/error feedback and `ui-empty-state` for empty/loading layouts. Preserve status/alert semantics.

### Dialogs and overlays

`Dialog` is the standard composition for modal tasks. It combines the existing `Modal` focus, portal, scroll lock and motion behavior with `DialogShell`, the single owner of the header, scrolling body and persistent footer. Use `DialogShell` only when an existing modal host or standalone confirmation already supplies the overlay. Do not rebuild headers, close buttons or action containers in feature components.

The default `small` width is 400px. Use `medium` (560px) for criteria and teacher assignment, and `large` (800px) for Information, field comparisons and technical details. Choose reading widths according to the amount of content. All are maximums bounded by the viewport with 15px margins. There is no extra-large variant or minimum content height. Only the body scrolls; header and actions remain visible. Media geometry and calibration targets are independent of these widths.

Dialog headers use `dialog-title`, with the dedicated `--dialog-title-size: 1.125rem` and `--dialog-title-leading: 1.5rem` tokens (18/24px at the default root size), weight 600. Panel headers use `default-title` (14/20px, weight 600); page titles and subordinate section headings keep their existing hierarchy. Body copy uses 14/20px, section headings and labels use weight 500, and secondary text uses 12/16px within dialogs. Informational annotations explicitly use the same compact 12/16px text. Padding is 15px, independent groups are 10px apart, and related labels, list items and supporting text use 5px. A footer supplies the single 15px separation before actions; do not combine an extra bottom margin or padding with it. Form actions are large shared buttons aligned right: Cancel then Save/Create, or a specific destructive label. Red is reserved for deletion.

`Dialog` accepts `title`, `open`, `onClose`, `busy`, `actions`, `hasDismissAction`, optional `onSubmit`, and a justified `size`. Set `hasDismissAction` whenever the footer provides Cancel, Close or another action returning to the parent view; the header then omits its redundant X. A footer with Save alone keeps the X. This explicit contract does not inspect localized button text and does not disable Escape. Pass native submit buttons through `actions` for forms. While busy, disable fields/actions and pass `busy` so the header, Escape and outside dismissal cannot interrupt saving. Otherwise Escape and the shared close button use the same cancel action; outside dismissal is off by default. Successful saves close and refresh the parent; errors preserve values. Required completion/resume notices deliberately omit `onClose` and retain their explicit navigation actions.

Keep score/comment editing focused on one component inside the existing results panel, replacing the table without opening a dialog. Hide the overall-score card while editing; show it again with persisted values on return. Keep only the component heading, left aligned, without a caption, followed by an initially closed criteria disclosure with a count badge and numbered list. Its chevron rotates from down to up through the left side (90 to 270 degrees), matching the other disclosure controls. Score and Comment labels use the existing neutral-500 color. Place the score label without helper text opposite an 80px decimal number input and scale, with native spinner arrows hidden only in this editor, then the required comment and large Cancel/Save actions on the right. Cancel discards local changes; successful Save refreshes results before returning. Failures retain values. The body switches with shared MotionContent (320ms opacity/12px translation) inside MotionHeight with fade disabled (420ms measured height), including asynchronous growth; header/source controls stay mounted. Reduced motion removes decoration. Focus the editor without scrolling to the score input, then restore focus to the pencil on return. All six scores and nonblank comments remain required by UI/API; partial drafts remain supported. Information shows every section directly, without disclosures. Compactness comes from text leading and spacing, not hiding primary information. Rubric references may remain optional disclosures. Use `dialog-list` for native numbered/bulleted lists; do not add grid/flex or separate margin utilities to list items, which hide markers or compound spacing. Teacher assignment lists all teachers without search. Clicking a row toggles its checkbox unless the assignment is locked. Status appears on the right without an additional lock message; long names and email addresses wrap instead of truncating. Case comparison pairs original and collected data by field, with two columns on desktop and one on mobile. Technical turn details use the global content maximum width, with general facts and the full transcript above two responsive paraverbal/nonverbal columns. All metrics remain visible without disclosures; mobile stacks the sections with natural scrolling. Clinical content, rubric wording, assessment permissions and capture timing do not change.

### Scores and date/time

Page-header dividers use the same 15px spacing on both sides. `ui-page-header` supplies `--layout-inset` above the border and adds only the difference between inset and gap as its bottom margin; the parent `ui-page` supplies the remaining gap below it. Do not add another margin around the divider.

When a listing's heading and actions already live in `PageHeader`, omit the `ListPanel` title and supply `titleId` pointing to that existing h1. The panel then renders pagination and content without a duplicate header. Users follows this pattern, with its large Create User action beside the page title.

`utils/evaluationScore.ts` owns the 0–5 range and bands: danger below 3, warning from 3 to below 4, success from 4. Do not duplicate thresholds. `EvaluationScore` supports `compact` (16px, the default) and `large` (30px), both weight 600. Its muted `/ 5` always uses `secondary-text`, separated by `--score-scale-gap: 0.25em`. Preserve one decimal and accessible score labels. Only its accompanying descriptive label is a badge.

`DateTime` preserves the existing local-time formatter with an English abbreviated month. Use stacked dates in table columns and inline dates for interview-summary start/end, messages and feedback. Missing data remains unavailable.

## Icons, colors and typography

Use exactly these eight typography utilities. Their size, weight and line-height come from the central `--type-size-*`, `--font-weight-*` and `--type-leading-*` tokens. Component rules compose the same utilities with `@apply`; layout and color remain separate.

Assessment results use the shared Select below the panel title, with no source buttons or tabs. Options are Text-based assessment, Assessment with multimodal evidence and Teacher: <name> in assignment order. Only the Teacher: prefix uses weight 600; the name stays at 400, both in the popup and selected value. A portal prevents clipping and repositions on scrolling/resizing. The control supports arrows, Home/End, typeahead, Enter/Space, Escape, Tab and outside dismissal. Only a superuser with the assignment capability sees Assign Teacher as the final option, entirely weight 600. Choosing it opens the existing assignment dialog without replacing the selected result. If a selected assignment is removed, fall back to Text-based assessment. With no assigned teachers, keep both automatic options available. Pending or missing teacher submissions remain unavailable, never zero scores.

Evaluation results reuse `ui-data-table`: Component, compact Score and a trailing disclosure action. Component names are underlined text actions opening the existing criteria dialog, including when feedback is collapsed; their accessible names identify the component. Each arrow expands the original feedback independently. The first visible component is labeled Overall performance (Desempeño general in Spanish), retaining the general_communication API key. Feedback has no separate View criteria or Edit score button. All result sources, including the own submitted rating, retain the trailing feedback disclosure arrow. Only the own rating adds a small pencil button immediately to the right of its score, opening the inline single-component editor without toggling feedback. Restore focus to that pencil on return, preserve expanded comments, and disable source switching during saving. Keep all six canonical categories, score bands, comparison access and Learning Moments behavior. Listing and evaluation tables retain their action columns but hide the last header label visually with `sr-only`, preserving its accessible name and all row actions.

Each criterion and its feedback share a tbody group and one hover surface. Clicking anywhere in the component summary row toggles feedback; nested buttons, links and form controls retain their own actions and never toggle the row a second time. Expanded groups remove the internal divider and the feedback cell's top padding, leaving one outer row boundary. Feedback disclosure arrows remain native keyboard-accessible buttons using the transparent `evaluation-feedback-toggle` with zero padding. Scores align left with the Score column heading. Case cards use a single native `case-disclosure-row` button covering number, description and decorative chevron; the expanded form/details remain outside that trigger.

Navigation uses one role-aware section from `getNavigationSection`, with matching active styling and `aria-current`. Teachers have Clinical Cases and Interviews in the top bar. Their Interviews page uses one table for owned and assigned interviews, without a view selector. The API merges and paginates the authorized rows; assigned reviews return to the same list. The former teacher `/students` path redirects to `/interviews`. Student and superuser scopes remain unchanged. Interview and user rows support click, Enter and Space, with visible focus; delete buttons stop propagation. Shared DateTime renders the date and local time on separate lines. The self-assessment instruction and send-audio coachmark reuse `dialog-annotation` for the pale blue notice style; the coachmark retains its pointing arrow. Full-screen calibration and active-call navigation restrictions remain unchanged.

Recap/evaluation headers use `ui-panel-header--title-sized`: the title determines row height. `panel-header-action` reserves horizontal space while its refresh button is positioned independently and centered vertically. Its icon follows the title line-height and the control retains the shared small icon padding; controls cannot increase the header's height. Warning colors, pending dots, tooltips and confirmations remain unchanged.

The overall-score summary places its heading and qualitative badge side by side on the left, with the badge immediately after the heading and the large numerical score and its scale aligned on the right. This layout applies to automatic and submitted teacher results; missing scores do not create an empty summary card.

| Utility | Size | Weight | Line height | Purpose |
| --- | --- | --- | --- | --- |
| `page-title` | 24px | 600 | 28px | Main page, authentication and calibration headings |
| `default-title` | 14px | 600 | 20px | Panel, section and subsection headings |
| `dialog-title` | 18px | 600 | 24px | Dialog headers only, through dedicated tokens |
| `default-text` | 14px | 400 | 20px | Body copy, input values, table data, names and dates |
| `medium-text` | 14px | 500 | 20px | Actions, tabs, field labels and brief emphasis |
| `secondary-text` | 12px | 400 | 20px | Captions, email addresses, hints and timestamps |
| `compact-text` | 12px | 500 | 20px | Badges and table column headings |
| `numeric-value` | 16px | 600 | 20px | Compact scores and numerical results |
| `metric-value` | 30px | 600 | 32px | Prominent statistics and large scores |

Typography sizes remain constant across viewport sizes; wrapping and layout handle responsive changes. Only weights 400, 500 and 600 are used. Native `strong` and `b` use 600 while inheriting their surrounding size. The declared primary font is Inter; the call timer retains its functional monospace family. Recording-canvas font sizes remain tied to the recorded frame geometry, outside the DOM typography catalog.

Do not introduce local font-size/weight combinations, responsive text-size utilities or legacy typography aliases such as `component-subtitle`, `ui-case-title`, `auth-eyebrow` or `text-timestamp`. Timestamps use `secondary-text` at 12px. Preserve semantic heading levels, accessible dialog labels and clinical casing.

Import icons directly from `lucide-react`; do not create local icon components, barrels or SVG copies. The default stroke is controlled by `--icon-stroke-width`; size and color follow shared CSS and `currentColor`. Decorative icons remain hidden from assistive technology; icon-only actions expose their name on the button.

Institutional logos and illustration assets remain assets. Synchronized media progress graphics are functional graphics, not an alternative icon set.

Keep the typography catalog, semantic brand/neutral/success/warning/danger palettes, radii and elevation. Unused legacy palette aliases have been removed. All interface text uses sentence case, including page/panel/dialog headings, navigation, table headings, actions, labels and states. Author this casing in the Spanish/English translations; do not use CSS capitalize/uppercase or runtime lowercasing. Preserve proper names, acronyms, scientific instrument names, units, interpolations and all user/API/clinical data verbatim.

Authentication, camera/microphone states, calibration targets, capture clocks and interview permissions keep their existing behavior. Dynamic waveform, progress and media coordinates remain custom properties or measured values, not additional visual variants.

Interview recap retains its horizontal dark playback bar, with elapsed time before the timeline and duration after it. The dedicated `recap-playback-button` shows only the play/pause icon, with transparent background and zero padding, matching the volume icon; the volume slider remains visible at all times. Both video badges sit at the top left with the shared inset. Selected transcript bubbles draw their highlight inside their bounds, and keyboard focus uses an inward outline to avoid clipping at scroll boundaries. `interview-summary-details` separates metadata rows with a 5px flex gap instead of sibling margins. Playback clocks, synchronized seeking, date formats and analysis permissions remain unchanged.

Recap transcript bubbles have uniformly rounded corners without tails or extra tail gutters. Bubble metadata shows the localized one-based conversation ordinal immediately before the elapsed timestamp; missing timestamps remain absent. These ordinals are display labels, not persisted turn IDs. The recap patient badge reads Patient/Paciente.

Bubble borders retain a stable 2px stroke across selection states, without an additional outer selection ring. Bubbles use content-sized width, capped at the smaller of 85% of their row and the shared `--chat-bubble-width` (500px). Student bubbles align right and patient bubbles align left; long words wrap inside the maximum width. The transcript is inline and metadata floats right at the end of the content, separated by the shared 10px gap. It shares the final text line when space permits and wraps as one unit otherwise. The bubble establishes a flow root to contain that float. Metadata remains one `secondary-text` line with uniform size, weight and color: Turn 1, 00:00. Only the bubble timestamp pads minutes to two digits; playback-bar formatting is unchanged. Omit both comma and timestamp when timing is unavailable.

Calibration preparation uses one aligned camera/device column. The preparation waveform and checklist are removed; face-centering, quiet-place and stable-device guidance appears in the introductory paragraph. That dialog has Back and Understood footer actions without a redundant X. Understood shows a disabled ten-second countdown, measured from a deadline so audio updates do not reset it; Back and Escape return to the case list immediately. Closing the dialog requires explicit acknowledgement and does not start capture. Cancel the timer on exit/unmount. Camera sound feedback is a layout-stable blue outline driven by the existing normalized audio level (visual threshold 0.08); it is not speech/quality validation and does not request another stream. Keep the functional waveform during the voice capture stage. Device statuses use left-aligned copy and a 5px internal gap. Only preparation preview layout changes; target coordinates, camera source, capture durations and calibration processing remain unchanged.

## Application motion

The entire application uses `common/Motion` through one `MotionProvider` in App, including sign-in, registration and portals. A display-contents wrapper supplies the explicit `data-ui-motion="app"` scope without changing layout geometry. Do not add animation libraries, route keys, duplicate outgoing routes, or artificial request delays.

The four central durations are `--app-motion-fast: 180ms` for controls, `--app-motion-enter: 320ms` for entries/content, `--app-motion-expand: 420ms` for disclosures, height changes and drawers, and `--app-motion-exit: 260ms` for dialog/menu exits. Reuse `--motion-panel-easing: cubic-bezier(0.2, 0.8, 0.2, 1)` and limit decorative translation to `--app-motion-distance: 12px`, without scale or bounce. Calibration targets and measured media geometry retain their functional definitions.

`MotionContent` fades a changed route using opacity without remounting children. Its opt-in `slide` mode is for conventional forms/panels only. Never transform camera/video containers, fixed calibration layers or entire interview layouts. `MotionHeight` observes natural content size and animates measured height and optional opacity, including asynchronous growth. Use `fade={false}` on whole-panel containers so child disclosures do not repeatedly dim the full panel. `MotionDetails` combines this behavior with native details/summary semantics and keyboard operation; keep the native surface open until its closing animation finishes.

Selectors reveal progressively with clip-path and vertical translation over 420ms, anchored to the field. Bottom menus expand downward and collapse upward; top menus reverse direction. Never use scaleY. Coordinate the chevron with the same duration. Dialogs/profile menus enter over 320ms and exit inversely over 260ms. `MotionPresence` retains outgoing dialog/menu content. `usePresence(open, exitToken)` defaults to `--app-motion-exit`; selectors and disclosures pass `--app-motion-expand` so their closing content remains mounted for all 420ms. Closed surfaces become inert and leave the accessibility tree immediately; modal focus and scroll locking remain until exit finishes. Reopening cancels pending removal, focus timers and previous animations.

`useEntrance` and `MotionRow` animate newly mounted cards/rows only, with `--app-motion-stagger: 35ms` between items and `--app-motion-stagger-limit: 140ms` maximum delay. Rows use opacity only; conventional cards may translate. Preserve stable item keys and never replay entries on polling, selection or reordering. Strict Mode effect replay cancels the first animation and starts the active one without leaving content invisible.

Keep existing rows and their displayed page/count together while fetching another page, block row actions and mark the region `aria-busy`. Commit the new rows/page/count together and ignore obsolete responses. Use accessible loading/error states without skeletons; do not use positive minimum heights to hide layout changes. Retain confirmed results during regeneration while disabling actions that depend on current evidence.

Only newly appended live messages animate. Playback, polling and turn selection must not replay their entry animation. `prefers-reduced-motion` disables decorative animations/transitions, translations, stagger delays and exit waits, and uses immediate scrolling; the preference updates while the application is open. Functional activity indicators remain available. Stop animations, observers, pending frames and presence timers on cleanup. These UI transitions never gate capture, calibration windows, requests or confirmations.

## Validation

Run within the existing UI Docker service:

```bash
docker compose -f docker-compose.local.yml exec ui yarn lint
docker compose -f docker-compose.local.yml exec ui yarn build
```

Use affected component tests and compiled-CSS assertions for geometry, states and cascade. Review mobile and desktop layouts, dialogs and loading/error states in a real browser when available. Static checks and jsdom tests do not constitute visual browser verification. Integrate dependencies through package.json/yarn.lock and rebuild the existing UI image; do not install project packages on the host.

## Mobile keyboards and text entry

All text-entry locations share `useInputViewport` at the App root: sign-in and
registration (Field), managed users (Field/Dialog), clinical hypotheses (FormInput/
DialogShell), manual scores and comments (HumanRatingPanel), and teacher feedback
(AddTeacherFeedbackModal). Range controls, checkboxes, read-only and disabled fields
are excluded from automatic text-field scrolling.

The viewport meta tag requests `interactive-widget=resizes-content` where supported.
The shared hook also publishes VisualViewport height/offset to CSS, with window resize
as fallback. App shell, authentication minimum height, modal overlay and dialog
maximum heights consume the same visible-height token. Modal bodies remain scrollable
between their header and action footer. On focus, input and viewport resize, an
occluded field scrolls by the nearest distance; visible fields are left alone.
Visual viewport panning updates overlay position without forcing a scroll. Events
are coalesced with requestAnimationFrame; listeners and inline tokens are cleaned
on unmount. Pinch zoom retains native zoom/panning behavior and is never disabled.
The viewport handler does not read input values or selection, change focus, or
persist participant content; it only inspects the active element, its type, state
and geometry.

Text inputs and textareas use at least 16px on narrow screens or devices with coarse
pointers. Scores request a decimal keyboard. Browser form validation, autocomplete,
password controls, focus containment and unsaved drafts retain their existing flow.

Simulated keyboard viewport changes are covered by unit tests and reduced-height
browser checks. Native iOS/iPadOS/Android keyboards, floating/split keyboards that do
not resize VisualViewport, and physical-device browser behavior still require manual
verification; desktop viewport emulation does not reproduce those keyboards.

Review layout keeps Information/Replay and Evaluation in two equal columns from
560px upward, including tablet portrait widths. Below 560px panels stack. The
shared breakpoint also controls the bounded information panel and its growing
transcript; the stacked transcript alone retains its maximum height. Recorded
patient/student videos remain horizontal with reserved aspect ratios.

Replay video elements have authenticated JPEG posters from
`GET /medical-interviews/{id}/recording/assets/{student_video|patient_video}/poster`.
The API shares the existing stream authorization and processing/completed gates,
then decodes only the first frame using FFmpeg already present in the API image.
The image is returned in memory with private/no-store headers: there is no new
stored media, retention rule, playback seek or autoplay. A failed preview leaves
the original media intact and returns a recoverable HTTP error. The browser can
show the initial frame without relying on iOS to decode a paused video at 0:00.
