# Live repository HTML download assertion

## Scope and acceptance

CI follow-up to Build [40100951448](https://github.com/hkrewson/TekDocs/actions/runs/40100951448)
at `60aae09fb3db81ecb356cf5bba477932b2826c2d`. Only the live journey failed;
extended validation 40100969699 and CodeQL 40100971427 passed.

The downloaded HTML must contain the saved repair instructions, exclude the
unsaved browser draft, retain the expected filename, and come from an HTTP 200
response with the saved Git commit and private/no-store cache policy. No
application, schema, API, dependency or release-version change is included.

## Verified reproduction before editing

A loopback HTTP server inside the existing `tekdocs-e2e-devtools:local` Docker
image served synthetic HTML with an attachment disposition. Chromium 156 under
Playwright 1.64.1 fetched it as a Blob and downloaded it through an object URL,
matching the application's export mechanism. Playwright `response.text()` was
empty, while the downloaded file contained the exact 51-byte HTML payload and
`download.failure()` was null. This reproduces the failing observation without
Django or PostgreSQL; it does not by itself prove the full application journey.
The hosted backend and proxy also logged HTTP 200 with 709 response bytes.

The synthetic probe and outputs are retained locally in the ignored
`artifacts/export-download-reproduction/` directory. Run the probe by mounting
its `tekdocs-export-probe.cjs` at `/tmp/export-probe.cjs` in that image and using
`node /tmp/export-probe.cjs`, with Docker networking disabled. Its loopback
server requires no credentials or application data. `PROBE_BODY` overrides the
synthetic HTML; `EXPECT_REJECTION=1` requires the content assertions to fail.

## Correction and focused evidence

The journey now waits for the download to finish, checks for download failure,
and reads the actual file. It retains the saved/unsaved content, filename,
HTTP status, commit and cache checks. Cleanup runs even if content validation
fails. It does not make a second request or substitute generated content.

Verified in Docker:

- Correct saved HTML passes the revised file assertions.
- An HTML file without the saved text is rejected.
- A file containing saved text plus the unsaved draft is rejected.
- ESLint for the changed journey and frontend type checking pass.

## Blocked validation and disposition

`make test-e2e-live` was attempted but stopped before browser execution while
building the renderer. A direct renderer build with plain output confirmed
`TAR_ENTRY_ERROR ENOSPC: no space left on device` during `npm ci`; Docker's
59 GiB filesystem then reported zero available space. No unrelated containers,
images or volumes were removed. Logs are retained at
`/tmp/tekdocs-live-export-before.log` and
`/tmp/tekdocs-export-build-blocker.log`; despite the first filename, the browser
stage was never reached and this is neither a full before nor after pass.

The full hosted live browser-to-PostgreSQL journey must confirm the correction.
No full runtime pass, upstream browser root cause, publication or deployment is
claimed. No public Wiki change is required for this internal test correction.
