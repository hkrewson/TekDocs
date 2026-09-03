# Interface language

TekDocs uses direct, familiar language for people doing MSP work. Interface text exists to name something, explain a necessary choice, prevent a mistake, or tell someone how to recover. It is not marketing copy and should not narrate the interface.

This contract governs words. The complete layout, hierarchy, density, control, responsive, and visual-consistency review is tracked separately in [issue #60](https://github.com/hkrewson/TekDocs/issues/60); wording and visual corrections should be delivered together when they touch the same workflow.

## Writing rules

- Use the shortest familiar term that remains accurate. Prefer **Invoices** over **Accounting**, **Invoice settings** over **Issuance settings**, and **Needs review** over **Reconciliation pending**.
- Name actions with a verb and an object: **Create invoice**, **Save settings**, **Publish document**, **Link device**.
- Use sentence case. Do not use decorative labels, slogans, conversational filler, or claims such as “seamless,” “powerful,” “intelligent,” or “effortless.”
- Do not expose implementation terms such as “surface,” “projection,” “canonical,” “artifact,” “payload,” “schema,” or “provider identity” unless the user is viewing a technical or audit detail where the distinction matters.
- Add help text only when it prevents a likely mistake, explains a consequence, or distinguishes two choices that otherwise look alike. Do not place a paragraph beneath every heading or control.
- Describe status as a concrete condition: **Not linked**, **Waiting for review**, **Published**, **Delivery failed**. Do not rely on color, icons, or vague labels such as **Active** when the underlying state is more specific.
- Errors say what failed, whether entered data was preserved, and what the user can do next. Use a stable support code only as secondary detail.
- Confirmations name the completed result. Avoid celebratory or anthropomorphic language.
- Destructive and security-sensitive actions state the affected object and consequence before confirmation.
- Icons supplement visible text unless the control is universally understood and has an accessible name and tooltip.

## Stable product terms

Use **MSP workspace**, **client workspace**, **document**, **template**, **publication**, **invoice**, **integration**, **connection**, and **review** consistently. Specialized terms such as **publication**, **baseline**, or **taxonomy** need one plain-language explanation at their first decision point; replacing them differently on each screen is worse than teaching one necessary term.

Internal API and database names do not dictate interface labels. Changing interface text does not authorize changing stable API fields, manifest keys, audit codes, or database identifiers.

## Review method

Audit one complete workflow at a time: navigation, page title, form labels, options, help, empty/loading/denied/error states, confirmation, notification, portal view, email, and generated output. Review screenshots at desktop and narrow widths, then complete the workflow with keyboard and screen-reader-accessible names enabled.

Copy changes use localization keys and receive component or browser assertions for consequential language. Snapshot or substring tests must protect meaning, not preserve awkward wording. A broad automated word replacement is not an acceptable audit.
