# Diagram migration source review

Fixed baseline: `b2e9cf57a828581f4adfb1884c6c9ea777ca23d4`. Review includes
working changes, new files and proposed ADR 0119 before the direct-main commit.

Independent Standards and Spec reviews are complete after reproduced corrections.
Source review does not substitute for Docker runtime or exact-source hosted validation.

## Standards

Standards re-review: **zero remaining actionable findings**.

The dedicated CI shard now mounts the existing renderer-job volume and starts
the same-project renderer before real-render tests. The fixture seeds distinct
diagram sources and checks source, SVG and PNG evidence differs; revision
fingerprints include immutable metadata. The publication view strips embedded
images, uses authorized artifact URLs for retained graphics, preserves accessible
source and avoids rerendering frozen diagrams. No additional documented-standard
breach or actionable heuristic smell found. Complete runtime/browser and hosted
validation remain required; this review does not establish their results.

## Spec

Spec re-review: **zero remaining concrete findings**.

Publication mode preserves the figure and accessible source, strips images
supplied by HTML, inserts graphics only from the existing authorized artifact
endpoint, and prevents frozen Mermaid source from being rerendered dynamically.
The fixture seeds distinct legacy graphs, asserts different source/SVG/PNG
checksums and fingerprints all retained revision metadata. The dedicated hosted
shard starts the renderer and mounts the shared job volume. No additional
incorrect implementation, missing scoped requirement or scope expansion found.
Complete backend, frontend, live-browser and exact-source hosted validation
remain separate pending gates; source review does not establish their results.

Final source-review counts: Standards 0, Spec 0.

## Reproductions and disposition

Reproductions retained:

- The initial legacy diagram publication test timed out because the test migrate
  service lacked the shared renderer-job mount. Current storage had ample space;
  old renderer ENOSPC logs are not a diagnosis of this attempt. The same real
  render succeeded after mounting the existing project volume.
- Valid signed legacy graphics were classified `publication_shape_unsupported`.
  After admission and byte checks, both history assessment and new Git snapshot
  tests passed.
- Missing/corrupt retained graphics raised an uncaught PublicationConflict during
  assessment. Four real-storage cases reproduced this; they now return blocked
  assessment and refuse import while preserving history.
- The publication Downloads interface omitted retained SVG/PNG. Its focused UI
  test reproduced missing links; the corrected view exposes the existing
  authorized downloads. Focused execution alone does not satisfy global frontend
  coverage; the complete frontend suite remains required.

- The dedicated CI shard initially lacked the renderer startup and shared job
  mount used by local tests. The actual unmounted real-render test reproduces
  the timeout; read-only Compose rendering now proves both services share the
  existing job volume, and the shard starts its same-project renderer. The full
  shard remains hosted-only under the local single-project rule.
- The two legacy fixture publications initially changed only prose. A real
  diagram-source checksum comparison reproduced equality. The first source now
  targets Archive rather than Server; the comparison passes, and seeding asserts
  distinct source, SVG and PNG checksums. Revision fingerprints now retain parent,
  creator, time and topic metadata as well as IDs, numbers, text and checksums.
- The publication sanitizer removed retained graphics. A public Documentation
  test reproduced the missing image. Publication mode now preserves semantic
  figure/source markup, strips all images supplied by HTML and uses only existing
  authorized retained-artifact URLs for React images. It never dynamically
  rerenders frozen source. The focused positive test passes; negative coverage
  strips embedded data/remote images and preserves source without live rendering.

- The extra template-source diagram test initially omitted required template
  history retention and correctly received `template_history_git_custody_unavailable`.
  The test now uses the existing prepare/retain history operations before handoff;
  its unchanged v11/v8 certificate and custody assertions pass. The gate was not
  weakened and no application fix is attributed to this fixture correction.


Subsequent local validation passed: 524 combined backend cases (two existing
opt-in skips), three additional cases, all 33 diagram cases, 781 frontend tests
and four real-browser journeys with server-side retained-byte and rollback
verification. Exact-source hosted validation remains pending; review alone does
not establish independent encrypted restore or production acceptance.


## Combined-core runner compatibility correction

After the first source push, read-only review confirmed the supported monolithic
`core` runner also selects the new real-render tests. Only the dedicated group
had received the renderer setup. Read-only Compose rendering reproduced its
missing job mount, matching the earlier actual unmounted-render timeout.
One shared `needs_diagram_renderer` flag now supplies the same existing project
mount and renderer startup to both `core` and `diagram-migration`. Test selection,
assertions and pre-existing matrix behavior are unchanged. Both reviewers cleared the actual corrective delta with zero findings;
exact-source CI must validate its new commit. Initial-source runs 41228633907,
41228636478 and 41228638894 were intentionally cancelled as superseded, rather
than being reported as failed tests or complete validation.


Final exact-source validation subsequently completed at
`5b7a9314866156ad731ee6e3c49c921b437a8e0a`: Build 41228928621, CodeQL
41228934806 and Extended 41228937218 all passed. The slice record links the
checked receipts, including all 33 diagram cases, four live journeys,
fresh/0.8.46 migration and independent encrypted recovery. Historical pending
statements above describe the review-time boundary; no required gate remains
pending for this runtime.
