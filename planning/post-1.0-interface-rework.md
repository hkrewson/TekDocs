# Post-1.0 end-to-end interface rework

Status: maintainer-requested first post-1.0 priority, November 2, 2026.

TekDocs should have its own coherent product identity and workflows. The
maintainer wants a top-to-bottom rework after the Git-backed document and 1.0
closeout, including a clear departure from inherited ITFlow interface patterns.
This is a product and interaction redesign, not a cosmetic theme pass.

## Intended scope

- Remove unnecessary explanatory prose; retain concise guidance where users
  need it to act, understand consequences or recover from an error.
- Improve button placement, action hierarchy, text-field layout, spacing and
  form grouping consistently across the product.
- Simplify complete task workflows and reduce avoidable steps, repeated entry
  and interruptions while preserving review and authorization boundaries.
- Simplify or collapse navigation around user tasks; resolve overlapping
  destinations and preserve discoverability, context and deep links.
- Modernize the visual language with a distinct TekDocs identity, consistent
  components and responsive behavior rather than copying ITFlow layouts.
- Cover the entire product journey: setup, MSP/client context, operational
  records, knowledge authoring/reuse, files, publications, portal and settings.

## Delivery approach

Begin with a route/action inventory and observed representative task journeys.
Agree the navigation model and interaction principles, then review a small set
of complete workflow prototypes before implementing a shared component system
and rolling through the product in bounded slices. Validate keyboard, touch,
screen-reader, zoom, loading, empty, conflict, denial and recovery states.

Measure the rework against agreed tasks: fewer unnecessary steps and duplicate
destinations, clearer primary actions, less redundant copy, consistent forms
and successful completion across supported viewport and input profiles. Do not
claim improvement from visual preference alone or hide required capabilities
and security decisions merely to make screens look simpler.

The 1.0 persistence and compatibility contract remains the foundation. Any
required behavioral/API change is reviewed explicitly. No redesign code or
new visual direction is selected by this planning record.
