# Document library and focused workspace

Phase 5 begins by separating document discovery from document work. The prior page kept the complete library above every open reader or editor, so selecting a record created two competing primary views and forced repeated long-page travel. The new flow presents the library until a document is opened, then replaces it with the focused document workspace and an explicit Documents return action.

## Implemented boundary

- The document search endpoint returns 25-record pages with canonical `page`, `page_size`, `count`, and `has_more` metadata.
- Search, category, collection, tag, health, document/template type, ordering, and page state restore from document-specific URL parameters.
- Title, update time, and category sorting are deterministic; text searches retain relevance ordering when the default title order is selected.
- Undeclared collection parameters are rejected, page size is capped, and search/filter visibility covers the complete authorized collection.
- The library reports the visible range, exposes pagination only when needed, and resets to page one when a search, filter, or order changes.
- An opened record is the sole primary view. Its reader/editor, settings, files, history, keys, publication, export, reuse, remote-source, and relationship tools remain available in the existing focused workspace.
- The selected document remains in the `document` URL parameter, including direct retrieval when it is outside the current library page. Back navigation restores the library.
- New layout rules ship with the lazy Documentation route instead of consuming the shell stylesheet budget.

## Remaining Phase 5 work

The template and reusable-content checkpoint is recorded in [template-and-block-workflows.md](template-and-block-workflows.md). The ownership/review checkpoint is recorded in [ownership-and-review.md](ownership-and-review.md). The grouped phase still needs static publication and export controls, and managed file/PDF workflows assessed and migrated as cohesive interface pieces. Full responsive matrices, direct-link history coverage, real-stack document creation/editing/publication/file journeys, and technician acceptance remain required before Phase 5 is accepted.
