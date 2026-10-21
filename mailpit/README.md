# Temporary Mailpit security rebuild

TekDocs 0.9.11 rebuilds unmodified Mailpit v1.31.6 source (commit
`a028b01f4a24b4b36bdad95b8e09e070ebf2bad4`) with Go 1.27.3. The source archive
is checksum-verified; Node, Go and Alpine build/runtime bases are digest-pinned.
`GOTOOLCHAIN=local` prevents an implicit toolchain download. Upstream lockfiles,
Go module checksums and embedded third-party license generation are retained.
No forked Mailpit application behavior is introduced.

## Why this exists

On October 21, 2026 both upstream v1.31.6 and edge images used Go 1.27.2 and
failed the HIGH/CRITICAL scan for CVE-2026-111943. The rebuilt binary uses Go
1.27.3 and x/net v0.61.0; neither the previous x/net exception nor a new Go
exception is needed. The final image starts from Alpine without the old binary.

Mailpit captures mail locally. It does **not** deliver to recipients' external
mailboxes. It remains the existing default until the operator configures real
SMTP. Keep the UI bound to loopback and SMTP on the internal Compose network.
The existing `/data/mailpit.db` volume and SMTP/API ports are unchanged.

## Release and maintenance

CI builds, scans, tests SMTP capture/restart persistence, and generates a Mailpit
SBOM. Authorized publication ships `ghcr.io/hkrewson/tekdocs-mailpit` alongside
the other images, with commit/version tags and signed provenance/SBOMs. The
reviewed release receipt includes a `mailpit=` digest; the updater checks source
revision, receipt equality and the running container before recording success.
Older three-image release receipts remain supported.

Dependabot covers Docker bases here. The maintainer must also review upstream
Mailpit releases and source/lockfile security updates; Docker-base updates alone
do not update the checksum-pinned application archive.

## Return to upstream

1. Inspect a new upstream stable image's SBOM and verify the fixed Go version
   and dependencies. Run an unsuppressed HIGH/CRITICAL scan; a newer tag alone
   is not sufficient evidence.
2. Simplify this Dockerfile to `FROM axllent/mailpit:<version>@sha256:<digest>`.
   Keep the TekDocs image wrapper for that release so production receipts,
   revision labels and automatic updates continue to work without operator
   Compose edits. Remove the source, Node and Go build stages.
3. Run `make mailpit-image-rehearsal`, the production image rehearsal and the
   release gates, including retained-volume behavior. Record the upstream
   digest, scanner results and removal of the temporary rebuild.
4. Publish through a freshly validated candidate and operator approval. A later
   separately reviewed change may retire the wrapper and fourth-image receipt;
   do not silently change the existing updater contract.

No publication or deployment has occurred merely because this source exists.
