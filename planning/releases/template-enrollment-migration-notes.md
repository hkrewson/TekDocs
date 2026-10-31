# Template enrollment migration — development notes

Development after 0.9.16; implementation, source review and local Docker/browser
validation are recorded in the [slice record](../migrations/template-enrollment-migration.md).
Its containing commit requires its own hosted validation receipt. No new application
version, image, production migration or Wiki publication is claimed.

- Reviewed migrations can move an approved MSP template and its enrolled client
  documents together. Independent copies, live sections, pinned sections, local
  edits, file versions, signed publications and PDFs retain their meanings.
- The template library shows current Git-backed section choices. Creation uses
  the reviewed source version; a changed or unavailable source requires another
  review. Existing accounts and Workspace permissions still govern every action.
- Enrolled documents offer template update checks and local copies of borrowed
  sections. Local edits remain conflicts for review. Pinned sections keep their
  selected text until an explicit update or local-copy action.
- Internal publications retain exact source proof and downloadable files/PDFs.
  Historical publications stay readable after later source edits or withdrawal.
- Missing source repositories produce an explicit retryable failure. General
  cross-Workspace reuse and client-portal editing/delivery are outside this slice.

Operator handoff and recovery procedures stay in internal engineering guidance.
