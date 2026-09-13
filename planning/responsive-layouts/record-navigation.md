# Shared record navigation — pre-1.0, 0.8.46

Scope: #78/#79 under #77, coordinated with #40. Extract the header and section controls already used by Assets into reusable components. Contracts and Networks remain the next consumers and must validate their own domain rules before their migration is complete. This is a foundation checkpoint, not closure of Phase 1, Assets, or the epic.

## Component contract

`frontend/src/records/RecordNavigation.tsx` exports `RecordHeader`, `RecordSections`, and the `RecordSection` type. Assets is the production consumer; there is no demonstration route or second competing implementation.

- A drawer supplies its own named dialog heading and initial heading focus, so an embedded AssetRecord omits the duplicate RecordHeader. It still uses RecordSections and the same guarded section content. See [asset-record-drawer.md](asset-record-drawer.md).
- The header takes a stable record identity, current section, title, and optional description. It focuses its heading when the record or section changes, without scrolling the page. Draft updates do not repeatedly steal focus.
- Section entries contain a stable identifier, translated label, and complete destination URL. Consumers supply only authorized entries and resolve an unknown or unavailable section to Overview before rendering. The component does not infer permissions, construct domain routes, or fetch content.
- Desktop section controls are ordinary links with `aria-current="page"`, retaining copy-link, bookmark, and new-tab behavior. Below 768 CSS pixels, the same destinations are available through the labeled Sections selector.
- Both navigation controls retain browser navigation state, including the owning collection's transient scroll/focus context. They use the existing router, so Back/Forward and the shared dirty-form guard remain authoritative. No substitute history entries or private guard implementation are added.
- The owning record still renders the labeled content region, urgent Overview warnings, per-section editors, and deferred reads. Asset-specific presentation adjustments remain scoped to `.asset-record`; the common width/wrapping and header styles use `.record-page` and `.record-header`.

Consumers must mount these controls beneath the application data router and shared NavigationGuardProvider. Register section drafts with the existing unsaved-change hook. A permission-hidden section must be removed from both the entries and rendered content; hiding navigation alone is not authorization. Domain permissions and server validation are unchanged.

## Verification sources

`RecordNavigation.test.tsx` covers deep-linked section state, exact link destinations, list-return state, Back/Forward, heading focus, and mobile section changes during a dirty edit. Keep editing retains the draft/current section; Discard changes clears the draft and completes the requested transition.

`Assets.test.tsx` retains the existing production integration and failed-edit checks. `asset-layout.spec.ts` now also verifies section-change focus and Back/Forward before refresh at all six maintained widths in Chromium, Firefox, and WebKit. Existing dirty-navigation, page/drawer overflow, accessibility, touch, and zoom-stress assertions remain. The isolated live workspace rehearsal exercises the extracted controls with Django and PostgreSQL, including hardware and software sections, assigned-site refresh, and subsequent workflows.

Final results are recorded in progress.md. No API, OpenAPI, model, migration, ownership/RLS, recovery-format, version, or deployment change is involved. No new scrolling surface is introduced.

## Remaining work

Validate reuse through Contracts (including cost permissions and separate currencies/intervals) and Networks (including parent/child detail navigation). Software audit history is implemented; see [software-history.md](software-history.md). Broader route/state coverage, technician/native zoom/screen-reader/mobile-keyboard walkthroughs, and applicable production/recovery/release gates remain open. This extraction does not make an unmigrated surface complete.
