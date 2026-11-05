### Keys and references in new Git documents

In a saved Git document, open **Keys and references**. Use **Binding name** and
**Find a record or reusable fragment**, then **Bind key** beside a permitted
record or fragment. Use **Insert key for …** to insert a field or reusable
fragment's content, or **Insert reference** to insert an entity card. Nested
fragment keys use the consuming document's bindings. Targets must belong to the
same Workspace. Use **Remove binding** to retire a declaration from the draft.

Choose **Save to Git** to save the bindings and Markdown together. A denied or
conflicting save keeps the draft. A changed saved source requires explicit reload;
review unsaved work first. Cancel an unfinished binding name before publishing.
The saved-source report shows resolved, withheld or unavailable states without
revealing field values. Promoted legacy bindings remain read-only.

Signed snapshots and publications retain their original field values, fragment
text, entity cards, files and PDFs after live records or bindings change. Clients
receive only the separately approved publication, not live keys or source proof.
This is 0.9.18 development functionality; it does not migrate existing documents
or constitute a production deployment.

New native content-key bindings accept native fragments only. Legacy Block-backed
fragments (including copied, promoted, rolled-back and archived sources) remain
in their existing workflow; their IDs cannot bypass legacy permissions through
a native binding. Existing documents and publications are not rewritten.
