# Native template enrollment — development notes

Development continues after published 0.9.18. This is not a new release or a
production deployment. Local validation and source review pass: 796 combined
backend cases, 883 frontend cases, and all 15 real browser/server journeys.
Exact-source hosted upgrade, encrypted recovery and security checks follow the push.

- Saved MSP Git documents can be enabled as templates, with explicitly selected
  native reusable sections offered in the existing client Templates tab.
- Clients choose copy, live or pinned sections. Introductions and local copies
  stay independent. Update review requires the exact source and destination
  versions; local replacement and detach are explicit choices.
- Signed publication evidence retains selected template source proof. Later
  source edits and enrollment changes cannot rewrite signed publications, PDFs
  or independent primary-file history.
- Existing data and legacy template workflows remain in place. Unsupported
  source dependencies fail explicitly instead of being copied without ownership
  or disclosure checks.

See [acceptance and evidence](../git-native-templates.md) and
[ADR 0127](../../docs/adr/0127-native-template-enrollment.md). Independent encrypted
restore and supported upgrades require exact-source hosted validation.
